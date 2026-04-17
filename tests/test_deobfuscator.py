import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import deobfuscator


ROOT = Path(__file__).resolve().parents[1]
COMPLEX_FIXTURES = ROOT / "deobfuscated_scripts_complex"


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


if __name__ == "__main__":
    unittest.main()
