import os
import sys
import re
from collections import Counter

from deobfuscator import LUA_KEYWORDS, lua_string, lua_tokens


def clean_dummy_name(name):
    return name


def parse_access_chain(name):
    return name.split(".")


def make_colon_call(obj_chain, method, args_str):
    return f"{obj_chain}:{method}({args_str})"


def simplify_call_result(line):
    m = re.match(r'^local\s+(\S+)\s*=\s*(.+)$', line)
    if not m:
        return line, None, False

    var_name = m.group(1)
    rhs = m.group(2).strip()

    call_match = re.match(r'^([a-zA-Z0-9_.]+)\((.*)\)$', rhs, re.DOTALL)
    if not call_match:
        return line, var_name, True

    func_chain = call_match.group(1)
    args_raw = call_match.group(2) or ""

    parts = func_chain.split(".")
    args_list = smart_split_args(args_raw)

    is_method_call = False
    clean_args = args_list

    if len(parts) >= 2 and len(args_list) >= 1:
        obj = ".".join(parts[:-1])
        method = parts[-1]
        first_arg = args_list[0].strip()

        if first_arg == obj:
            is_method_call = True
            clean_args = args_list[1:]

    if is_method_call:
        obj = ".".join(parts[:-1])
        method = parts[-1]
        obj = simplify_obj_name(obj)
        args_str = ", ".join(a.strip() for a in clean_args)
        args_str = re.sub(r'function:\s*[0-9a-fA-F]+', 'function(...)', args_str)
        call_expr = f"{obj}:{method}({args_str})"
        nice_var = generate_var_name(obj, method, clean_args)
        return call_expr, nice_var, True
    else:
        func_name = simplify_obj_name(func_chain)
        args_str = ", ".join(a.strip() for a in args_list)
        args_str = re.sub(r'function:\s*[0-9a-fA-F]+', 'function(...)', args_str)
        call_expr = f"{func_name}({args_str})"
        nice_var = generate_var_name_from_func(func_name, args_list)
        return call_expr, nice_var, True


def smart_split_args(args_str):
    result = []
    depth = 0
    start = 0
    for token in lua_tokens(args_str):
        if token.kind in ("string", "longstring"):
            continue
        if token.text in ("(", "{", "["):
            depth += 1
        elif token.text in (")", "}", "]"):
            depth -= 1
        elif token.text == "," and depth == 0:
            result.append(args_str[start:token.start])
            start = token.end
    if args_str[start:].strip():
        result.append(args_str[start:])
    return result


def simplify_obj_name(name):
    name = re.sub(r'_\d{3,}$', '', name)
    return name


def generate_var_name(obj, method, args):
    if method == "GetService" and len(args) >= 1:
        return args[0].strip().strip('"').strip("'")

    if method == "FindFirstChild" and len(args) >= 1:
        return args[0].strip().strip('"').strip("'")

    if method == "FindFirstChildOfClass" and len(args) >= 1:
        return args[0].strip().strip('"').strip("'").lower()

    if method == "WaitForChild" and len(args) >= 1:
        return args[0].strip().strip('"').strip("'")

    if method == "Connect":
        return None

    if method == "GetMouse":
        return "mouse"

    if method == "GetPlayers":
        return "playerList"

    if method == "GetChildren":
        return "children"

    if method == "GetDescendants":
        return "descendants"

    return method[0].lower() + method[1:] if method else None


def generate_var_name_from_func(func_name, args):
    if "Instance.new" in func_name and len(args) >= 1:
        class_name = args[0].strip().strip('"').strip("'")
        return class_name[0].lower() + class_name[1:]

    if "Vector3.new" in func_name:
        return None

    if "Vector2.new" in func_name:
        return None

    if "UDim2.new" in func_name:
        return None

    if "Color3" in func_name:
        return None

    if "CFrame" in func_name:
        return None

    if "task.wait" in func_name:
        return None

    base = func_name.split(".")[-1]
    return base[0].lower() + base[1:] if base else None


def detect_loops(lines):
    if len(lines) < 6:
        return None

    for pattern_len in range(2, min(20, len(lines) // 2 + 1)):
        pattern = []
        for i in range(pattern_len):
            pattern.append(normalize_for_pattern(lines[i]))

        count = 1
        pos = pattern_len
        while pos + pattern_len <= len(lines):
            matches = True
            for j in range(pattern_len):
                if normalize_for_pattern(lines[pos + j]) != pattern[j]:
                    matches = False
                    break
            if matches:
                count += 1
                pos += pattern_len
            else:
                break

        if count >= 3 and count * pattern_len >= len(lines) * 0.8:
            return pattern_len, count, lines[:pattern_len]

    return None


def normalize_for_pattern(line):
    line = re.sub(r'_\d{3,}', '_XXX', line)
    line = re.sub(r'Service_\w+', 'Service_XXX', line)
    return line


def parse_trace(report_file):
    with open(report_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    constants_str = ""
    trace_lines = []
    in_constants = False
    in_trace = False

    for line in lines:
        raw_line = line.rstrip("\r\n")
        line = line.strip()
        if not line:
            continue

        if line == "--- CONSTANTS START ---" or line == "--- CONSTANTS ---":
            in_constants = True
            continue
        if line == "--- CONSTANTS END ---":
            in_constants = False
            continue
        if line == "--- TRACE ---":
            in_trace = True
            continue
        if line == "--- TRACE END ---":
            in_trace = False
            continue

        if in_constants:
            constants_str += raw_line + "\n"
        elif in_trace or any(line.startswith(prefix) for prefix in [
            "CALL_RESULT -->", "SET GLOBAL -->", "TRACE_PRINT -->",
            "URL DETECTED -->", "--- ENTERING CLOSURE", "--- EXITING CLOSURE",
            "ACCESSED -->", "LOADSTRING DETECTED", "LOADSTRING CONTENT",
            "PROP_SET -->", "PRINT_CALL -->", "RETURN -->", "CLOSURE_ARGS -->"
        ]):
            trace_lines.append(line)

    operations = []
    closure_stack = []

    for line in trace_lines:
        if line.startswith("CALL_RESULT -->"):
            code = line.split("CALL_RESULT -->", 1)[1].strip()
            operations.append({"type": "call", "raw": code, "depth": len(closure_stack)})

        elif line.startswith("SET GLOBAL -->"):
            code = line.split("SET GLOBAL -->", 1)[1].strip()
            operations.append({"type": "set_global", "raw": code, "depth": len(closure_stack)})

        elif line.startswith("TRACE_PRINT -->"):
            msg = line.split("TRACE_PRINT -->", 1)[1].strip()
            operations.append({"type": "print", "raw": msg, "depth": len(closure_stack)})

        elif line.startswith(("PRINT_CALL -->", "RETURN -->")):
            code = line.split(" -->", 1)[1].strip()
            operations.append({"type": "statement", "raw": code, "depth": len(closure_stack)})

        elif line.startswith("CLOSURE_ARGS -->"):
            operations.append({"type": "closure_args", "raw": line.split(" -->", 1)[1].strip()})

        elif line.startswith("URL DETECTED -->"):
            url = line.split("URL DETECTED -->")[1].strip()
            operations.append({"type": "url", "raw": url, "depth": len(closure_stack)})

        elif line.startswith("--- ENTERING CLOSURE FOR"):
            func_name = line.replace("--- ENTERING CLOSURE FOR ", "").replace(" ---", "").strip()
            operations.append({"type": "closure_start", "name": func_name, "depth": len(closure_stack)})
            closure_stack.append(func_name)

        elif line.startswith("--- EXITING CLOSURE FOR"):
            operations.append({"type": "closure_end", "depth": len(closure_stack) - 1})
            if closure_stack:
                closure_stack.pop()

        elif line.startswith("PROP_SET -->"):
            code = line.split("PROP_SET -->", 1)[1].strip()
            operations.append({"type": "prop_set", "raw": code, "depth": len(closure_stack)})

        elif line.startswith("LOADSTRING DETECTED"):
            operations.append({"type": "loadstring", "raw": line, "depth": len(closure_stack)})

    lua_lines = []
    var_counter = {}
    var_map = {}
    used_vars = set()
    references = Counter(token.text for operation in operations
                         for token in lua_tokens(operation.get("raw", "")) if token.kind == "name")
    used_vars.update(references)

    closure_info_stack = []
    for index, operation in enumerate(operations):
        indent = "    " * len(closure_info_stack)
        kind = operation["type"]
        if kind == "call":
            declared = re.match(r"local\s+(\w+)", operation["raw"])
            keep_result = declared is not None and references[declared.group(1)] > 1
            line = process_call_line(operation["raw"], var_map, var_counter, used_vars, keep_result)
            if index + 1 < len(operations) and operations[index + 1]["type"] == "closure_start":
                placeholder = "function(...) end"
                if placeholder in line:
                    before, after = line.split(placeholder, 1)
                    line = before + "function(...)"
                    operations[index + 1]["inline_close"] = "end" + after
            lua_lines.append(indent + line)
        elif kind == "statement":
            lua_lines.append(indent + resolve_vars(operation["raw"], var_map))
        elif kind == "print":
            lua_lines.append(indent + "print(" + lua_string(operation["raw"]) + ")")
        elif kind == "set_global":
            lua_lines.append(indent + process_set_global(operation["raw"], var_map))
        elif kind == "prop_set":
            lua_lines.append(indent + process_prop_set(operation["raw"], var_map))
        elif kind == "closure_start":
            closing = operation.get("inline_close")
            if closing is None:
                lua_lines.append(indent + "local function callback(...)")
                closing = "end"
            closure_info_stack.append(closing)
            if index + 1 >= len(operations) or operations[index + 1]["type"] != "closure_args":
                lua_lines.append(indent + "    local arg1, arg2, arg3, arg4 = ...")
        elif kind == "closure_args":
            lua_lines.append(indent + "local " + operation["raw"] + " = ...")
        elif kind == "closure_end" and closure_info_stack:
            closing = closure_info_stack.pop()
            lua_lines.append("    " * len(closure_info_stack) + closing)

    output_lines = []

    if constants_str.strip():
        output_lines.append("do\n" + "\n".join("    " + line for line in constants_str.strip().splitlines()) + "\nend")
        output_lines.append("")

    output_lines.extend(lua_lines)

    final_output = "\n".join(output_lines)
    final_output = postprocess_output(final_output)

    out_file = report_file.replace(".report.txt", ".deobf.lua")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(final_output)

    print(f"Saved {out_file}")


def process_call_line(raw, var_map, var_counter, used_vars, keep_result=True):
    m = re.match(r'^local\s+(\S+)\s*=\s*(.+)$', raw)
    if not m:
        return raw

    orig_var = m.group(1)
    rhs = m.group(2).strip()

    resolved_rhs = resolve_vars(rhs, var_map)

    call_match = re.match(r'^([a-zA-Z0-9_.]+)\((.*)\)$', resolved_rhs, re.DOTALL)
    if not call_match:
        clean_name = get_clean_var(orig_var, var_counter, used_vars)
        var_map[orig_var] = clean_name
        return f"local {clean_name} = {resolved_rhs}"

    func_chain = call_match.group(1)
    args_raw = call_match.group(2) or ""

    parts = func_chain.split(".")
    args_list = smart_split_args(args_raw)

    is_method = False
    obj_str = ""
    method_str = ""
    clean_args = args_list

    if len(parts) >= 2 and len(args_list) >= 1:
        obj_str = ".".join(parts[:-1])
        method_str = parts[-1]
        first_arg = args_list[0].strip()

        if first_arg == obj_str:
            is_method = True
            clean_args = args_list[1:]

    clean_arg_strs = []
    for a in clean_args:
        a = a.strip()
        if re.fullmatch(r"function:\s*[0-9a-fA-F]+", a):
            a = "function(...) end"
        clean_arg_strs.append(a)
    args_str = ", ".join(clean_arg_strs)

    if is_method:
        call_expr = f"{obj_str}:{method_str}({args_str})"
    else:
        call_expr = f"{func_chain}({args_str})"

    if is_method:
        nice_name = generate_var_name(obj_str, method_str, clean_arg_strs)
    else:
        nice_name = generate_var_name_from_func(func_chain, clean_arg_strs)

    if not keep_result:
        return call_expr
    if not nice_name:
        nice_name = parts[-2].lower() if len(parts) > 1 and parts[-1] == "new" else "result"

    if nice_name:
        nice_name = re.sub(r"[^a-zA-Z0-9_]", "_", nice_name)
        if not nice_name or nice_name[0].isdigit() or nice_name in LUA_KEYWORDS:
            nice_name = "value_" + nice_name

    if nice_name:
        if nice_name in used_vars:
            count = var_counter.get(nice_name, 1) + 1
            while f"{nice_name}{count}" in used_vars:
                count += 1
            var_counter[nice_name] = count
            final_name = f"{nice_name}{count}"
        else:
            final_name = nice_name
            var_counter[nice_name] = 1

        used_vars.add(final_name)
        var_map[orig_var] = final_name
        return f"local {final_name} = {call_expr}"


def resolve_vars(text, var_map):
    tokens = lua_tokens(text)
    for index in range(len(tokens) - 1, -1, -1):
        token = tokens[index]
        is_member = index > 0 and tokens[index - 1].text in (".", ":")
        is_key = index + 1 < len(tokens) and tokens[index + 1].text == "=" and index > 0 and tokens[index - 1].text in ("{", ",", ";")
        if token.kind == "name" and token.text in var_map and not is_member and not is_key:
            text = text[:token.start] + var_map[token.text] + text[token.end:]
    return text


def get_clean_var(orig_var, var_counter, used_vars):
    parts = orig_var.split("_")

    while parts and parts[-1].isdigit():
        parts.pop()

    if not parts:
        name = "var"
    else:
        name = parts[-1]
        if name[0].isupper():
            name = name[0].lower() + name[1:]

    if name in used_vars:
        count = var_counter.get(name, 1) + 1
        var_counter[name] = count
        name = f"{name}{count}"

    used_vars.add(name)
    return name


def process_set_global(raw, var_map):
    m = re.match(r'^(\S+)\s*=\s*(.+)$', raw)
    if not m:
        return raw

    var_name = m.group(1)
    value = resolve_vars(m.group(2).strip(), var_map)

    return f"{var_name} = {value}"


def process_prop_set(raw, var_map):
    resolved = resolve_vars(raw, var_map)
    return resolved


def postprocess_output(output):
    return output.strip() + "\n"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        parse_trace(sys.argv[1])
    else:
        for file in os.listdir("obfuscated_scripts"):
            if file.endswith(".report.txt"):
                parse_trace(os.path.join("obfuscated_scripts", file))
