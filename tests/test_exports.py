import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import test_deobfuscation


ROOT = Path(__file__).resolve().parents[1]


class ExportTests(unittest.TestCase):
    def test_exports_only_verified_code_into_the_shared_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "tests/fixtures"
            shutil.copytree(
                ROOT / "tests/fixtures",
                fixtures,
                ignore=shutil.ignore_patterns("deobfuscated", "*.report.txt", "*.deobf.lua"),
            )

            with patch.object(test_deobfuscation, "ROOT", root):
                with contextlib.redirect_stdout(io.StringIO()):
                    test_deobfuscation.save_outputs()

            outputs = fixtures / "deobfuscated"
            self.assertTrue(outputs.is_dir())
            manifest = json.loads((outputs / "manifest.json").read_text())
            self.assertEqual(len(manifest["samples"]), 12)
            self.assertFalse(list(outputs.rglob("*.report.txt")))
            self.assertFalse(any("report" in entry for entry in manifest["samples"]))

            expected = {Path("manifest.json")}
            for entry in manifest["samples"]:
                output = root / entry["output"]
                self.assertTrue(output.is_file())
                expected.add(output.relative_to(outputs))

            actual = {path.relative_to(outputs) for path in outputs.rglob("*") if path.is_file()}
            self.assertEqual(actual, expected)

    def test_default_runner_regenerates_outputs_after_tests_pass(self):
        result = unittest.TestResult()
        with patch("sys.argv", ["test_deobfuscation.py"]):
            with patch.object(unittest.TextTestRunner, "run", return_value=result):
                with patch.object(test_deobfuscation, "save_outputs") as save:
                    self.assertEqual(test_deobfuscation.main(), 0)
        save.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
