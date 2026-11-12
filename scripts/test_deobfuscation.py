import argparse
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import deobfuscator


def save_outputs():
    fixtures = ROOT / "tests/fixtures"
    expectations = json.loads((fixtures / "expectations.json").read_text())
    samples = []
    for source in expectations:
        platform, filename = source.split("/")
        for provider in ("wearedevs", "prometheus/medium", "prometheus/strong"):
            samples.append(fixtures / "obfuscated" / platform / provider / filename)
    samples.sort()
    manifest = {
        "scope": "Executed fixture behavior, exact expected strings and typed constants",
        "roblox_environment": "Mocked services and one callback invocation with four mock arguments",
        "universal_deobfuscation": False,
        "samples": [],
    }
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory)
        for sample in samples:
            relative = sample.relative_to(fixtures / "obfuscated")
            working = staging / relative
            working.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sample, working)
            with contextlib.redirect_stdout(io.StringIO()):
                if not deobfuscator.deobfuscate_file(str(working)):
                    raise RuntimeError(f"Deobfuscation failed: {sample}")
            generated = Path(str(working) + ".deobf.lua")
            output = generated.read_bytes()
            working.write_bytes(output)
            generated.unlink()
            Path(str(working) + ".report.txt").unlink()
            manifest["samples"].append({
                "input": sample.relative_to(ROOT).as_posix(),
                "output": (Path("tests/fixtures/deobfuscated") / relative).as_posix(),
                "sha256": hashlib.sha256(output).hexdigest(),
                "strings_and_constants_verified": True,
                "runtime_operations_match_source": True,
                "standalone_stdout_and_returns_match": True if relative.parts[0] == "non_roblox" else None,
            })
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        shutil.copytree(staging, fixtures / "deobfuscated", dirs_exist_ok=True)
    print(f"Saved {len(samples)} verified outputs to tests/fixtures/deobfuscated/")


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    save_outputs()
    return 0


if __name__ == "__main__":
    sys.exit(main())
