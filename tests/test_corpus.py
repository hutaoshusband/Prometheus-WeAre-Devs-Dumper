import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import deobfuscator


FIXTURES = Path(__file__).parent / "fixtures"
EXPECTATIONS = json.loads((FIXTURES / "expectations.json").read_text())
VARIANTS = ("wearedevs", "prometheus/medium", "prometheus/strong")
CONSTANT_PROBE = """
for _, value in ipairs(Constants) do
    local kind = type(value)
    if kind == "string" then
        local encoded = value:gsub(".", function(character)
            return string.format("%02x", string.byte(character))
        end)
        print("string:" .. encoded)
    elseif kind == "number" then
        print("number:" .. string.format("%.17g", value))
    elseif kind == "boolean" then
        print("boolean:" .. tostring(value))
    end
end
"""


def run_lua(source):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "probe.lua"
        path.write_text(source)
        return subprocess.run([deobfuscator.get_lua_executable(), str(path)],
                              capture_output=True, check=True, timeout=10).stdout


def assert_sample(test, sample, expected):
    with tempfile.TemporaryDirectory() as directory:
        working = Path(directory) / sample.name
        shutil.copy2(sample, working)
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            success = deobfuscator.deobfuscate_file(str(working))
        test.assertTrue(success, log.getvalue())
        report = Path(str(working) + ".report.txt").read_text()
        test.assertNotIn("CLOSURE ERROR", report)
        constants = report.split("--- CONSTANTS ---\n", 1)[1]
        test.assertTrue(constants.isascii())
        values = set(run_lua(constants + CONSTANT_PROBE).decode().splitlines())
        for value in expected["strings"]:
            test.assertIn("string:" + value.encode("utf-8").hex(), values,
                          f"missing string {value!r} in {sample}")
        for value in expected["binary_hex"]:
            test.assertIn("string:" + value, values)
        for value in expected["numbers"]:
            test.assertIn("number:" + format(value, ".17g"), values)
        for value in expected["booleans"]:
            test.assertIn("boolean:" + str(value).lower(), values)
        output = Path(str(working) + ".deobf.lua")
        text = output.read_text()
        for operation in expected["code"]:
            test.assertIn(operation, text)
        test.assertFalse(any(token.lastgroup in ("comment", "longcomment")
                             for token in deobfuscator.TOKEN_PATTERN.finditer(text)))
        command = "assert(loadfile(" + deobfuscator.lua_string(str(output)) + "))"
        subprocess.run([deobfuscator.get_lua_executable(), "-e", command],
                       check=True, capture_output=True, timeout=10)
        return text


class CorpusTests(unittest.TestCase):
    def test_all_providers_recover_exact_strings_constants_and_operations(self):
        for relative_source, expected in EXPECTATIONS.items():
            platform, filename = relative_source.split("/")
            for variant in VARIANTS:
                with self.subTest(platform=platform, source=filename, provider=variant):
                    sample = FIXTURES / "obfuscated" / platform / variant / filename
                    self.assertTrue(sample.is_file(), f"missing fixture: {sample}")
                    assert_sample(self, sample, expected)

    def test_standalone_reconstruction_preserves_stdout_and_returns(self):
        for relative_source, expected in EXPECTATIONS.items():
            if not relative_source.startswith("non_roblox/"):
                continue
            original = FIXTURES / "source" / relative_source
            for variant in VARIANTS:
                with self.subTest(source=relative_source, provider=variant):
                    sample = FIXTURES / "obfuscated/non_roblox" / variant / original.name
                    output = assert_sample(self, sample, expected)
                    baseline = deobfuscator.normalize_luau_syntax(original.read_text())
                    trailer = '\nlocal values = {run()}\nfor i = 1, 3 do print(type(values[i]), values[i]) end\n'
                    self.assertEqual(run_lua("local function run()\n" + baseline + "\nend" + trailer),
                                     run_lua("local function run()\n" + output + "\nend" + trailer))

    def test_source_programs_execute_in_native_luau(self):
        runtime = os.environ.get("LUAU_EXECUTABLE") or shutil.which("luau")
        self.assertTrue(runtime, "Luau is required for corpus validation; set LUAU_EXECUTABLE")
        for source in sorted((FIXTURES / "source/non_roblox").glob("*")):
            with self.subTest(source=source.name):
                result = subprocess.run([runtime, str(source)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(result.stdout, run_lua(deobfuscator.normalize_luau_syntax(source.read_text())))
                for variant in VARIANTS:
                    sample = FIXTURES / "obfuscated/non_roblox" / variant / source.name
                    output = assert_sample(self, sample, EXPECTATIONS["non_roblox/" + source.name])
                    with tempfile.TemporaryDirectory() as directory:
                        reconstructed = Path(directory) / "reconstructed.luau"
                        reconstructed.write_text(output)
                        replay = subprocess.run([runtime, str(reconstructed)], capture_output=True, timeout=10)
                        self.assertEqual(replay.returncode, 0, replay.stderr.decode())
                        self.assertEqual(replay.stdout, result.stdout)

    def test_provenance_matches_sources_and_outputs(self):
        for relative_source in EXPECTATIONS:
            platform, filename = relative_source.split("/")
            for variant in VARIANTS:
                with self.subTest(source=relative_source, provider=variant):
                    sample = FIXTURES / "obfuscated" / platform / variant / filename
                    metadata = json.loads(Path(str(sample) + ".json").read_text())
                    source = FIXTURES / "source" / relative_source
                    self.assertEqual(metadata["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                    self.assertEqual(metadata["output_sha256"], hashlib.sha256(sample.read_bytes()).hexdigest())
                    if variant.startswith("prometheus/"):
                        self.assertRegex(metadata["commit"], r"^[0-9a-f]{40}$")
                        self.assertEqual(metadata["seed"], 20261112)
                    else:
                        self.assertEqual(metadata["provider"], "wearedevs")

    def test_reconstruction_replays_the_source_runtime_operations(self):
        for relative_source, expected in EXPECTATIONS.items():
            platform, filename = relative_source.split("/")
            source = FIXTURES / "source" / relative_source
            original = deobfuscator.normalize_luau_syntax(source.read_text())
            baseline, errors, status = deobfuscator.run_chunk(original)
            self.assertEqual(status, 0, errors)
            expected_trace = deobfuscator.read_sections(baseline)[1]
            for variant in VARIANTS:
                with self.subTest(source=relative_source, provider=variant):
                    sample = FIXTURES / "obfuscated" / platform / variant / filename
                    output = assert_sample(self, sample, expected)
                    replay, errors, status = deobfuscator.run_chunk(output)
                    self.assertEqual(status, 0, errors)
                    self.assertEqual(deobfuscator.read_sections(replay)[1], expected_trace)


if __name__ == "__main__":
    unittest.main()
