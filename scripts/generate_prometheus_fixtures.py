import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deobfuscator import get_lua_executable


def generate(checkout, presets, seed):
    dirty = subprocess.check_output(
        ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"], text=True
    ).strip()
    if dirty:
        raise RuntimeError("Prometheus checkout has tracked changes; use a clean checkout for provenance")
    commit = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    runtime = get_lua_executable()
    runtime_version = subprocess.check_output(
        [runtime, "-e", "io.write(jit and jit.version or _VERSION)"], text=True
    )
    for source in sorted((ROOT / "tests/fixtures/source").glob("*/*")):
        for preset in presets:
            config = (checkout / "src/presets.lua").read_text()
            with tempfile.TemporaryDirectory() as directory:
                config_path = Path(directory) / "config.lua"
                config_path.write_text(
                    "local presets = (function()\n" + config + "\nend)()\n"
                    f'local config = presets["{preset}"]\n'
                    f"config.Seed = {seed}\nreturn config\n"
                )
                destination = (
                    ROOT / "tests/fixtures/obfuscated" / source.parent.name
                    / "prometheus" / preset.lower() / source.name
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [runtime, str(checkout / "cli.lua"),
                     "--config", str(config_path), "--nocolors",
                     "--LuaU" if source.suffix == ".luau" else "--Lua51",
                     "--out", str(destination), str(source)],
                    cwd=checkout, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                metadata = {
                    "provider": "prometheus",
                    "repository": "https://github.com/prometheus-lua/Prometheus",
                    "commit": commit,
                    "preset": preset,
                    "seed": seed,
                    "generator_runtime": runtime_version,
                    "lua_version": "LuaU" if source.suffix == ".luau" else "Lua51",
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "output_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                }
                destination.with_suffix(destination.suffix + ".json").write_text(
                    json.dumps(metadata, indent=2) + "\n"
                )
                print(destination.relative_to(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--preset", nargs="+", choices=("Weak", "Medium", "Strong"),
                        default=["Medium", "Strong"])
    parser.add_argument("--seed", type=int, default=20261112)
    args = parser.parse_args()
    generate(args.checkout.resolve(), args.preset, args.seed)


if __name__ == "__main__":
    main()
