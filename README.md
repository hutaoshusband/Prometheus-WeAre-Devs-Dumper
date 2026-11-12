# Prometheus WeAreDevs Reconstruction... actually? Yeah, nothing more.

Prometheus obfuscator and WeAreDevs.net Obfuscator can be reconstructed using this project, but with some limits.

It runs the code in a mocked environment, catches decoded strings and constants, and reconstructs the operations it sees. Roblox services get stunt doubles. Your original variable names can not be reconstructed, also not executed paths cannot as well, for now.

## Feed it some spaghetti

You need Python 3.9+ and **Lua 5.1 or LuaJIT**. Windows binaries are included in `lua_bin/`. Elsewhere, install either runtime or point `LUA51_EXECUTABLE` at it. The complete test suite also needs the native Luau CLI, available through `PATH` or `LUAU_EXECUTABLE`.

```sh
python3 deobfuscator.py path/to/script.lua
python3 deobfuscator.py path/to/script.luau
python3 deobfuscator.py path/to/directory
```

## Obfuscated Tests
```text
tests/fixtures/
  source/
    non_roblox/{lua.lua,luau.luau}
    roblox/{lua.lua,luau.luau}
  obfuscated/
    non_roblox/
      wearedevs/
      prometheus/{medium,strong}/
    roblox/
      wearedevs/
      prometheus/{medium,strong}/
  deobfuscated/
    non_roblox/
      wearedevs/
      prometheus/{medium,strong}/
    roblox/
      wearedevs/
      prometheus/{medium,strong}/
    manifest.json
  expectations.json
```

All presets included.

The JSON files beside the obfuscated samples record their provider, settings and hashes. Prometheus fixtures use commit `a98c50165f2a53f6d765a82eee60dfea53803445` and seed `20261112` from [prometheus-lua/Prometheus](https://github.com/prometheus-lua/Prometheus). WeAreDevs does not publish its exact revision or preset, so its metadata records the service banner and manual submission instead.

## Run shit tests

```sh
python3 scripts/test_deobfuscation.py
```

This runs the tests, then automatically regenerates the committed deobfuscated files when they pass. The exporter saves code and a verification manifest. Its trace reports exist only in temporary directories.

Tests cover exact string bytes, UTF-8, quotes, backslashes, empty strings, binary bytes, numbers, booleans and values after `nil` arguments. All 12 samples must recover the expected values and reproduce the source's runtime operations under the same mock environment. Standalone results must preserve stdout and return values, and both the source and recovered programs run in native Luau.

To rebuild the Prometheus samples too:
```sh
git clone https://github.com/prometheus-lua/Prometheus.git /tmp/prometheus
git -C /tmp/prometheus checkout a98c50165f2a53f6d765a82eee60dfea53803445
python3 scripts/generate_prometheus_fixtures.py /tmp/prometheus
python3 scripts/test_deobfuscation.py
```

For fresh WeAreDevs samples, submit the matching files from `source/` to [the obfuscator](https://wearedevs.net/obfuscator) and update their provenance JSON files.

## Something you will LOVE!

Aesthetic recovery is planned for another repository. We will rewrite the deobfuscator completely there, with the goal of fully automatic static reverse engineering and readable structure recovery. That work is still ahead of us. This repository is the current trace-based playground and test bench.

Greetings from **WBB-Group**. May all your scripts be reversed and... whatever. Join the Discord Server: [Discord](https://discord.com/invite/dUCNKkS2Ve)
