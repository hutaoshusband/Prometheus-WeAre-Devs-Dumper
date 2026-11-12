import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import deobfuscator


ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def test_recursive_lua_and_luau_batch_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            (root / "plain.lua").write_text('print("plain")')
            (nested / "compound.luau").write_text('local n = 2; n *= 3; print("luau", n)')
            command = [sys.executable, str(ROOT / "deobfuscator.py"), str(root)]
            for _ in range(2):
                process = subprocess.run(command, cwd=directory, capture_output=True, timeout=10)
                self.assertEqual(process.returncode, 0, process.stdout.decode() + process.stderr.decode())
                self.assertEqual(len(list(root.rglob("*.deobf.lua"))), 2)
                self.assertEqual(len(list(root.rglob("*.report.txt"))), 2)

    def test_invalid_runtime_override_is_an_actionable_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "sample.lua"
            sample.write_text('print("sample")')
            environment = dict(os.environ, LUA51_EXECUTABLE=str(sample.parent / "missing-lua"))
            process = subprocess.run([sys.executable, str(ROOT / "deobfuscator.py"), str(sample)],
                                     env=environment, capture_output=True, timeout=10)
            self.assertEqual(process.returncode, 1)
            self.assertIn(b"Lua 5.1 or LuaJIT is required", process.stdout)

    def test_compile_failure_returns_nonzero_and_keeps_report(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "broken.lua"
            sample.write_text("local =")
            process = subprocess.run([sys.executable, str(ROOT / "deobfuscator.py"), str(sample)],
                                     capture_output=True, timeout=10)
            self.assertEqual(process.returncode, 1)
            self.assertIn("COMPILE ERROR", Path(str(sample) + ".report.txt").read_text())


if __name__ == "__main__":
    unittest.main()
