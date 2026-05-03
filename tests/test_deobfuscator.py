import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import deobfuscator
import trace_to_lua


ROOT = Path(__file__).resolve().parents[1]
COMPLEX_FIXTURES = ROOT / "deobfuscated_scripts_complex"
OBFUSCATED_FIXTURES = ROOT / "obfuscated_scripts"


class DeobfuscatorRegressionTests(unittest.TestCase):
    def test_normalize_luau_syntax_rewrites_compound_assignments(self):
        source = "foo+=1 bar.baz-=delta tbl[idx]*=scale"

        rewritten = deobfuscator.normalize_luau_syntax(source)

        self.assertIn("foo = foo + 1", rewritten)
        self.assertIn("bar.baz = bar.baz - delta", rewritten)
        self.assertIn("tbl[idx] = tbl[idx] * scale", rewritten)

    def test_complex_fixtures_emit_traceful_code(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            working_copy = Path(tmp_dir) / "complex"
            shutil.copytree(COMPLEX_FIXTURES, working_copy)

            result = subprocess.run(
                [sys.executable, "deobfuscator.py", str(working_copy)],
                cwd=ROOT,
                capture_output=True,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            self.assertEqual(
                result.returncode,
                0,
                msg=f"{stdout}\n{stderr}",
            )

            generated = sorted(working_copy.glob("*.deobf.lua"))
            self.assertEqual(len(generated), 4)

            interesting_tokens = (
                "game:GetService",
                "Instance.new",
                "task.",
                ":Connect(",
                ":WaitForChild(",
                "Color3.",
                "UDim2.",
            )

            for output_file in generated:
                text = output_file.read_text(encoding="utf-8", errors="replace")
                non_comment_lines = [
                    line
                    for line in text.splitlines()
                    if line.strip() and not line.lstrip().startswith("--")
                ]
                code_lines = [
                    line for line in non_comment_lines if not line.startswith("local Constants =")
                ]

                self.assertTrue(
                    code_lines,
                    msg=f"{output_file.name} only produced constants/header:\n{text[:1000]}",
                )
                self.assertTrue(
                    any(token in text for token in interesting_tokens),
                    msg=f"{output_file.name} did not recover meaningful Lua code:\n{text[:1000]}",
                )

    def test_complex_fixture_constants_are_ascii_safe(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            working_copy = Path(tmp_dir) / "complex"
            shutil.copytree(COMPLEX_FIXTURES, working_copy)

            subprocess.run(
                [sys.executable, "deobfuscator.py", str(working_copy)],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

            for report_file in sorted(working_copy.glob("*.report.txt")):
                text = report_file.read_text(encoding="utf-8", errors="replace")
                constants_section = text.split("--- CONSTANTS ---", 1)[1]
                self.assertFalse(
                    any(ord(char) > 127 for char in constants_section),
                    msg=f"{report_file.name} still contains non-ASCII constant data:\n{constants_section[:1500]}",
                )

    def test_large_lua51_control_structure_falls_back_to_static_constants(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "large_control.luau"
            oversized_block = " ".join("a=1" for _ in range(70000))
            sample.write_text(
                '--[[ v1.0.0 https://wearedevs.net/obfuscator ]] '
                'return(function(...)local z={"\\065","\\066"} '
                f"if false then {oversized_block} end end)"
                "(getfenv and getfenv()or _ENV)",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, "deobfuscator.py", str(sample)],
                cwd=ROOT,
                capture_output=True,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            self.assertEqual(result.returncode, 0, msg=f"{stdout}\n{stderr}")
            self.assertIn("using static string-table fallback", stdout)
            self.assertNotIn("STDERR:", stdout)

            report = sample.with_name(sample.name + ".report.txt")
            deobfuscated = sample.with_name(sample.name + ".deobf.lua")
            self.assertIn('[1] = "A"', report.read_text(encoding="utf-8"))
            self.assertIn('[2] = "B"', deobfuscated.read_text(encoding="utf-8"))

    def test_known_wearedevs_sample_keeps_decoded_constants_and_code(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "known_decoded.lua"
            shutil.copy2(
                OBFUSCATED_FIXTURES / "obfuscated_script-1771597947527.lua",
                sample,
            )

            result = subprocess.run(
                [sys.executable, "deobfuscator.py", str(sample)],
                cwd=ROOT,
                capture_output=True,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            self.assertEqual(result.returncode, 0, msg=f"{stdout}\n{stderr}")

            deobfuscated = sample.with_name(sample.name + ".deobf.lua")
            text = deobfuscated.read_text(encoding="utf-8", errors="replace")
            for token in (
                "Tamper Detected!",
                "FindFirstChild",
                "GetService",
                "FireServer",
                "I LOVE Gravity!",
            ):
                self.assertIn(token, text)

    def test_local_obfuscated_fixture_batch_still_produces_outputs(self):
        source_files = [
            path
            for path in sorted(OBFUSCATED_FIXTURES.glob("*.lua"))
            if ".deobf." not in path.name and ".report." not in path.name
        ]
        self.assertGreaterEqual(len(source_files), 10)

        with tempfile.TemporaryDirectory() as tmp_dir:
            working_copy = Path(tmp_dir) / "obfuscated"
            working_copy.mkdir()
            for source_file in source_files:
                shutil.copy2(source_file, working_copy / source_file.name)

            result = subprocess.run(
                [sys.executable, "deobfuscator.py", str(working_copy)],
                cwd=ROOT,
                capture_output=True,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            self.assertEqual(result.returncode, 0, msg=f"{stdout}\n{stderr}")

            generated = sorted(working_copy.glob("*.deobf.lua"))
            self.assertEqual(len(generated), len(source_files))
            for output_file in generated:
                text = output_file.read_text(encoding="utf-8", errors="replace")
                self.assertIn("-- Deobfuscated via Trace Emulation", text)
                self.assertGreater(
                    len(text),
                    30,
                    msg=f"{output_file.name} produced empty-looking output",
                )

    def test_trace_to_lua_parses_colon_calls_and_split_args(self):
        raw_call = 'local abc_123 = game:GetService("Players")'
        call_expr, var_name, is_method = trace_to_lua.simplify_call_result(raw_call)

        self.assertTrue(is_method)
        self.assertEqual(call_expr, raw_call)
        self.assertEqual(var_name, "abc_123")

        args = trace_to_lua.smart_split_args('"a,b", wrapper("x,y"), 42')
        self.assertEqual(args[0], '"a,b"')
        self.assertEqual(args[1], ' wrapper("x,y")')
        self.assertEqual(args[2], ' 42')

        lines = [
            "ACCESSED --> game",
            "CALL_RESULT --> local a = game:GetService()",
            "ACCESSED --> task",
            "CALL_RESULT --> local b = task.wait(1)",
            "ACCESSED --> game",
            "CALL_RESULT --> local a = game:GetService()",
            "ACCESSED --> task",
            "CALL_RESULT --> local b = task.wait(1)",
            "ACCESSED --> game",
            "CALL_RESULT --> local a = game:GetService()",
            "ACCESSED --> task",
            "CALL_RESULT --> local b = task.wait(1)",
        ]
        loop_info = trace_to_lua.detect_loops(lines)
        self.assertIsNotNone(loop_info)
        self.assertEqual(loop_info[0], 4)
        self.assertGreaterEqual(loop_info[1], 3)


if __name__ == "__main__":
    unittest.main()
