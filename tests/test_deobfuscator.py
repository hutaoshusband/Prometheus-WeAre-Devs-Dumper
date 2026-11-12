import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import deobfuscator
import trace_to_lua


ROOT = Path(__file__).resolve().parents[1]


class DeobfuscatorRegressionTests(unittest.TestCase):
    def test_normalize_luau_syntax_rewrites_compound_assignments(self):
        source = "foo+=1 bar.baz-=delta tbl[idx]*=scale"

        rewritten = deobfuscator.normalize_luau_syntax(source)

        self.assertIn("foo = foo + 1", rewritten)
        self.assertIn('= bar; local __deobf_key_1 = "baz"', rewritten)
        self.assertIn("= tbl; local __deobf_key_2 = idx", rewritten)

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

            self.assertEqual(result.returncode, 1, msg=f"{stdout}\n{stderr}")
            self.assertIn("using static string-table fallback", stdout)
            self.assertNotIn("STDERR:", stdout)

            report = sample.with_name(sample.name + ".report.txt")
            deobfuscated = sample.with_name(sample.name + ".deobf.lua")
            self.assertIn('[1] = "A"', report.read_text(encoding="utf-8"))
            self.assertIn('[2] = "B"', deobfuscated.read_text(encoding="utf-8"))

    def test_deobfuscator_safely_handles_http_substring_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "http_substring.luau"
            sample.write_text(
                '--[[ v1.0.0 https://wearedevs.net/obfuscator ]] '
                'return(function(...)local env = ...; local z={"http", "www", "https://google.com/search?q=test"} '
                'for _, url in ipairs(z) do env.table.concat({url}, "") end end)'
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
            self.assertNotIn("STDERR:", stdout)
            self.assertIn("URL DETECTED IN CONCAT --> https://google.com/search?q=test", stdout)

    def test_mocked_string_char_tolerates_dummy_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "dummy_string_char.luau"
            sample.write_text(
                '--[[ v1.0.0 https://wearedevs.net/obfuscator ]] '
                'return(function(...)local env = ...; local z={"A"} '
                'local B = env.string.char; B(env.game) end)'
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
            self.assertNotIn("STDERR:", stdout)
            self.assertTrue(sample.with_name(sample.name + ".deobf.lua").exists())

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
