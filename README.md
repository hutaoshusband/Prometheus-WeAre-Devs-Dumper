# Prometheus WeAreDevs Dumper

A trace-based deobfuscator designed to reconstruct the original logic and string constants from Roblox scripts, particularly those obfuscated on WeAreDevs and similar platforms. It simulates a custom mock environment to hook environment calls and translates traces back into readable Lua code.

## Requirements

- Python 3.x

*(Note: The required Lua 5.1 executable is already included in the repository)*

## Usage

To deobfuscate a single file:
```cmd
python deobfuscator.py path/to/script.lua
```

To automatically format all `.lua` files in a directory:
```cmd
python deobfuscator.py path/to/directory
```

If you just run `python deobfuscator.py`, it will default to processing all scripts inside the `obfuscated_scripts` folder.

## Example

A quick comparison of a script before and after going through the trace emulation:

Obfuscated:
https://end2end.space/pastes/QxU3Atz6GPoD/raw

Deobfuscated:
https://end2end.space/pastes/CSsl7lSSpqz2
