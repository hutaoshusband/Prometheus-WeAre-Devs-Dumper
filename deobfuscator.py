import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parent
LUA_CONTROL_STRUCTURE_TOO_LONG = "control structure too long"
COMPOUND_ASSIGNMENT_OPERATORS = ("+=", "-=", "*=", "/=", "%=", "..=", "^=")
LUA_KEYWORDS = frozenset(
    (
        "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
        "if", "in", "local", "nil", "not", "or", "repeat", "return", "then", "true",
        "until", "while",
    )
)
TOKEN_PATTERN = re.compile(
    r"(?P<longcomment>--\[(?P<ceq>=*)\[.*?\](?P=ceq)\])"
    r"|(?P<comment>--[^\n]*)"
    r"|(?P<longstring>\[(?P<seq>=*)\[.*?\](?P=seq)\])"
    r"|(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
    r"|(?P<name>[a-zA-Z_][a-zA-Z_0-9]*)"
    r"|(?P<number>0[xX][0-9a-fA-F]+(?:\.[0-9a-fA-F]+)?(?:[pP][+-]?\d+)?"
    r"|(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"|(?P<operator>\.\.=|\.\.\.|[+*/%^=-]=|~=|<=|>=|\.\.|\S)",
    re.DOTALL,
)


class Token(NamedTuple):
    kind: str
    text: str
    start: int
    end: int


def lua_tokens(source):
    tokens = []

    for match in TOKEN_PATTERN.finditer(source):
        if match.lastgroup in ("comment", "longcomment"):
            continue

        tokens.append(
            Token(match.lastgroup, match.group(), match.start(), match.end())
        )

    return tokens


def lua_string(value):
    parts = []

    for byte in value.encode("utf-8"):
        if byte in (34, 92):
            parts.append("\\" + chr(byte))
        elif 32 <= byte <= 126:
            parts.append(chr(byte))
        else:
            parts.append(f"\\{byte:03d}")

    return '"' + "".join(parts) + '"'


def get_lua_executable():
    configured = os.environ.get("LUA51_EXECUTABLE")

    if configured:
        candidates = [configured]
    else:
        candidates = []

        if os.name == "nt":
            candidates.append(str(ROOT / "lua_bin/lua5.1.exe"))

        for name in ("lua5.1", "lua51", "luajit", "lua"):
            executable = shutil.which(name)
            if executable:
                candidates.append(executable)

    for executable in candidates:
        try:
            result = subprocess.run(
                [executable, "-e", 'io.write(_VERSION)'],
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue

        if result.returncode == 0 and result.stdout == b"Lua 5.1":
            return executable

    raise RuntimeError(
        "Lua 5.1 or LuaJIT is required; set LUA51_EXECUTABLE to its path"
    )


def _matching_bracket(tokens, start):
    closing_brackets = {"(": ")", "[": "]", "{": "}"}
    expected = []

    for index in range(start, len(tokens)):
        token = tokens[index]

        if token.kind in ("string", "longstring"):
            continue

        if token.text in closing_brackets:
            expected.append(closing_brackets[token.text])
        elif token.text in closing_brackets.values():
            if not expected or token.text != expected.pop():
                return None
            if not expected:
                return index

    return None


def _find_table_literal_end(source, open_brace_index):
    tokens = lua_tokens(source[open_brace_index:])
    closing_index = _matching_bracket(tokens, 0)

    if closing_index is None:
        return -1

    return open_brace_index + tokens[closing_index].end


def constant_tables(source):
    tokens = lua_tokens(source)
    literal_tokens = {"true", "false", "nil", ",", ";", "-", "+"}

    for index in range(len(tokens) - 3):
        declaration, variable, assignment, opening = tokens[index:index + 4]

        if declaration.text != "local" or variable.kind != "name":
            continue
        if assignment.text != "=" or opening.text != "{":
            continue

        closing_index = _matching_bracket(tokens, index + 3)
        if closing_index is None:
            continue

        values = tokens[index + 4:closing_index]
        contains_only_literals = all(
            token.kind in ("number", "string", "longstring")
            or token.text in literal_tokens
            for token in values
        )

        if values and contains_only_literals:
            yield variable.text, opening.start, tokens[closing_index].end


def instrument_constants(source):
    tables = list(constant_tables(source))

    for _, start, end in reversed(tables):
        literal = source[start:end]
        source = source[:start] + f"__capture_table({literal})" + source[end:]

    return source


def extract_static_constants(source, variable_name):
    for name, start, end in constant_tables(source):
        if name != variable_name:
            continue

        literal = source[start:end]
        capture = f"local values = __capture_table({literal}); return nil"
        stdout, _, _ = run_chunk(capture)
        constants, _ = read_sections(stdout)
        return constants.strip()

    return ""


def _rhs_end(tokens, start):
    binary_operators = {
        "+", "-", "*", "/", "%", "^", "..", "and", "or",
        "==", "~=", "<", ">", "<=", ">=",
    }
    unary_operators = {"-", "#", "not"}
    index = start
    needs_value = True

    while index < len(tokens):
        token = tokens[index]

        if token.text in ("(", "{", "["):
            closing_index = _matching_bracket(tokens, index)
            if closing_index is None:
                break

            index = closing_index + 1
            needs_value = False
        elif needs_value and (
            token.text in unary_operators
            or token.kind in ("name", "number", "string", "longstring")
        ):
            needs_value = token.text in unary_operators
            index += 1
        elif not needs_value and token.text in binary_operators:
            needs_value = True
            index += 1
        elif not needs_value and token.text in (".", ":") and index + 1 < len(tokens):
            index += 2
        else:
            break

    return index


def _prefix_start(tokens, end):
    token = tokens[end]

    if token.kind == "name" and token.text not in LUA_KEYWORDS:
        if end >= 2 and tokens[end - 1].text in (".", ":"):
            return _prefix_start(tokens, end - 2)
        return end

    if token.text not in ("]", ")"):
        return None

    opening_bracket = "[" if token.text == "]" else "("
    depth = 1
    start = end - 1

    while start >= 0:
        previous = tokens[start]

        if previous.kind not in ("string", "longstring"):
            if previous.text == token.text:
                depth += 1
            elif previous.text == opening_bracket:
                depth -= 1
                if depth == 0:
                    break

        start -= 1

    if start < 0:
        return None

    previous = tokens[start - 1] if start > 0 else None
    if previous is not None:
        follows_identifier = (
            previous.kind == "name" and previous.text not in LUA_KEYWORDS
        )
        follows_bracket = previous.text in ("]", ")")

        if follows_identifier or follows_bracket:
            return _prefix_start(tokens, start - 1)

    return start if token.text == ")" else None


def _compound_target(source, tokens, start, operator_index):
    last_token = tokens[operator_index - 1]

    if last_token.text == "]":
        for index in range(start, operator_index):
            if tokens[index].text != "[":
                continue
            if _matching_bracket(tokens, index) == operator_index - 1:
                base = source[tokens[start].start:tokens[index].start]
                key = source[tokens[index].end:last_token.start]
                return base, key
    else:
        base = source[tokens[start].start:tokens[operator_index - 2].start]
        return base, lua_string(last_token.text)


def _rewrite_indexed_assignment(base, key, operator, expression, names):
    suffix = 1

    while f"__deobf_object_{suffix}" in names or f"__deobf_key_{suffix}" in names:
        suffix += 1

    object_name = f"__deobf_object_{suffix}"
    key_name = f"__deobf_key_{suffix}"
    names.update((object_name, key_name))
    target = f"{object_name}[{key_name}]"

    return (
        f"do local {object_name} = {base}; "
        f"local {key_name} = {key}; "
        f"{target} = {target} {operator} {expression} end"
    )


def normalize_luau_syntax(source):
    tokens = lua_tokens(source)
    names = {token.text for token in tokens if token.kind == "name"}
    replacements = []

    for index, token in enumerate(tokens):
        if token.kind != "operator":
            continue
        if token.text not in COMPOUND_ASSIGNMENT_OPERATORS:
            continue

        start = _prefix_start(tokens, index - 1)
        if start is None:
            continue

        end = _rhs_end(tokens, index + 1)
        if end == index + 1:
            continue

        target = source[tokens[start].start:token.start].strip()
        value = source[tokens[index + 1].start:tokens[end - 1].end]
        expression = value if end == index + 2 else f"({value})"
        operator = token.text[:-1]
        replacement = f"{target} = {target} {operator} {expression}"

        if index - start > 1:
            base, key = _compound_target(source, tokens, start, index)
            replacement = _rewrite_indexed_assignment(
                base, key, operator, expression, names
            )

        replacements.append((tokens[start].start, tokens[end - 1].end, replacement))

    for start, end, replacement in reversed(replacements):
        source = source[:start] + replacement + source[end:]

    return source


def run_chunk(source, timeout=20):
    executable = get_lua_executable()
    runtime = ROOT / "lua_runtime.lua"

    with tempfile.TemporaryDirectory(prefix="lua-trace-") as directory:
        input_path = Path(directory) / "input.lua"
        input_path.write_text(source, encoding="utf-8")

        process = subprocess.Popen(
            [executable, str(runtime), str(input_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            stderr += b"\nExecution timed out"

    return (
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
        process.returncode,
    )


def read_sections(stdout):
    constants = []
    trace = []
    in_constants = False

    for line in stdout.splitlines():
        if line == "--- CONSTANTS START ---":
            in_constants = True
        elif line == "--- CONSTANTS END ---":
            in_constants = False
        elif in_constants:
            constants.append(line)
        else:
            trace.append(line)

    return "\n".join(constants), trace


def _recover_static_constants(source, stdout, trace, constants):
    failed_compile = any(line.startswith("COMPILE ERROR") for line in trace)
    if not failed_compile or LUA_CONTROL_STRUCTURE_TOO_LONG not in stdout:
        return constants

    first_table = next(constant_tables(source), None)
    if first_table is None:
        return constants

    recovered = extract_static_constants(source, first_table[0])
    if recovered:
        print(
            "Lua 5.1 could not compile the full script; "
            "using static string-table fallback."
        )
        return recovered

    return constants


def _write_report(path, constants, trace):
    report = Path(str(path) + ".report.txt")
    sections = [
        "--- DEOBFUSCATION REPORT ---",
        f"File: {path}",
        "",
        "--- TRACE ---",
        *trace,
        "--- TRACE END ---",
        "",
        "--- CONSTANTS ---",
        constants,
        "",
    ]
    report.write_text("\n".join(sections), encoding="utf-8")
    return report


def deobfuscate_file(filepath):
    path = Path(filepath)

    if ".deobf." in path.name or ".report." in path.name:
        return True

    print(f"Processing {path}...")

    try:
        source = path.read_text(encoding="utf-8")
        normalized = normalize_luau_syntax(source)
        instrumented = instrument_constants(normalized)
        stdout, stderr, return_code = run_chunk(instrumented)
    except (OSError, RuntimeError, UnicodeError) as error:
        print(f"Error: {error}")
        return False

    constants, trace = read_sections(stdout)
    constants = _recover_static_constants(normalized, stdout, trace, constants)

    if stderr:
        trace.append("EXECUTION ERROR --> " + stderr.strip())

    for line in trace:
        print(line)

    report = _write_report(path, constants, trace)

    import trace_to_lua

    trace_to_lua.parse_trace(str(report))
    return return_code == 0 and not stderr


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=Path("obfuscated_scripts"),
    )
    target = parser.parse_args(argv).target

    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(
            path
            for path in target.rglob("*")
            if path.suffix in (".lua", ".luau")
            and ".deobf." not in path.name
            and ".report." not in path.name
        )
    else:
        parser.error(f"path does not exist: {target}")

    success = True

    for path in files:
        if not deobfuscate_file(str(path)):
            success = False

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
