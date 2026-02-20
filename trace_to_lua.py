import os
import sys
import re
from collections import OrderedDict


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
    current = ""
    in_string = False
    string_char = None

    for ch in args_str:
        if in_string:
            current += ch
            if ch == string_char:
                in_string = False
            continue

        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            current += ch
        elif ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            result.append(current)
            current = ""
        else:
            current += ch

    if current.strip():
        result.append(current)

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
            constants_str += line + "\n"
        elif in_trace or any(line.startswith(prefix) for prefix in [
            "CALL_RESULT -->", "SET GLOBAL -->", "TRACE_PRINT -->",
            "URL DETECTED -->", "--- ENTERING CLOSURE", "--- EXITING CLOSURE",
            "ACCESSED -->", "LOADSTRING DETECTED", "LOADSTRING CONTENT",
            "PROP_SET -->"
        ]):
            trace_lines.append(line)

    operations = []
    closure_stack = []

    for line in trace_lines:
        if line.startswith("CALL_RESULT -->"):
            code = line.split("CALL_RESULT -->")[1].strip()
            operations.append({"type": "call", "raw": code, "depth": len(closure_stack)})

        elif line.startswith("SET GLOBAL -->"):
            code = line.split("SET GLOBAL -->")[1].strip()
            operations.append({"type": "set_global", "raw": code, "depth": len(closure_stack)})

        elif line.startswith("TRACE_PRINT -->"):
            msg = line.split("TRACE_PRINT -->")[1].strip()
            operations.append({"type": "print", "raw": msg, "depth": len(closure_stack)})

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
            code = line.split("PROP_SET -->")[1].strip()
            operations.append({"type": "prop_set", "raw": code, "depth": len(closure_stack)})

        elif line.startswith("LOADSTRING DETECTED"):
            operations.append({"type": "loadstring", "raw": line, "depth": len(closure_stack)})

    lua_lines = []
    var_counter = {}
    var_map = {}
    used_vars = set()

    top_level_calls = [op for op in operations if op["type"] == "call" and op["depth"] == 0]
    loop_info = detect_loops([op["raw"] for op in top_level_calls])

    if loop_info:
        pattern_len, repeat_count, pattern_lines = loop_info
        lua_lines.append(f"-- Loop detected: {repeat_count} iterations")
        lua_lines.append(f"while true do")

        for raw_line in pattern_lines:
            clean_line = process_call_line(raw_line, var_map, var_counter, used_vars)
            if clean_line:
                lua_lines.append(f"    {clean_line}")

        lua_lines.append("end")
        lua_lines.append("")

        loop_end_idx = pattern_len * repeat_count
        remaining_ops = [op for i, op in enumerate(operations)
                        if not (op["type"] == "call" and op["depth"] == 0 and
                               operations.index(op) < loop_end_idx * (len(operations) / len(top_level_calls) if top_level_calls else 1))]
    else:
        closure_info_stack = []
        i = 0
        while i < len(operations):
            op = operations[i]
            in_closure = len(closure_info_stack)
            indent = "    " * in_closure

            if op["type"] == "call":
                clean_line = process_call_line(op["raw"], var_map, var_counter, used_vars)
                if clean_line:
                    skip = False
                    CONSTRUCTOR_PREFIXES = ("UDim2.new", "Color3.fromRGB", "Color3.new",
                                           "Vector3.new", "Vector2.new", "CFrame.new",
                                           "BrickColor.new", "NumberRange.new")
                    if any(clean_line.startswith(p) for p in CONSTRUCTOR_PREFIXES):
                        if i + 1 < len(operations) and operations[i+1]["type"] == "prop_set":
                            next_raw = operations[i+1]["raw"]
                            if clean_line in next_raw or clean_line.split("(")[0] in next_raw:
                                skip = True

                    if not skip:
                        if i + 1 < len(operations) and operations[i+1]["type"] == "closure_start":
                            if "function(...) end)" in clean_line:
                                clean_line = clean_line.replace("function(...) end)", "function(...)")
                                operations[i+1]["inline_close"] = "end)"
                            elif "function(...) end" in clean_line:
                                clean_line = clean_line.replace("function(...) end", "function(...)")
                                operations[i+1]["inline_close"] = "end"
                        lua_lines.append(f"{indent}{clean_line}")

            elif op["type"] == "set_global":
                clean_line = process_set_global(op["raw"], var_map)
                if clean_line:
                    lua_lines.append(f"{indent}{clean_line}")

            elif op["type"] == "print":
                msg = op["raw"].replace('\\', '\\\\').replace('"', '\\"')
                lua_lines.append(f'{indent}print("{msg}")')

            elif op["type"] == "url":
                lua_lines.append(f'{indent}-- URL: {op["raw"]}')

            elif op["type"] == "prop_set":
                clean_line = process_prop_set(op["raw"], var_map)
                if clean_line:
                    lua_lines.append(f"{indent}{clean_line}")

            elif op["type"] == "closure_start":
                inline_close = op.get("inline_close")
                if inline_close is not None:
                    closure_info_stack.append(inline_close)
                else:
                    closure_name = op["name"]
                    lua_lines.append(f"{indent}-- Closure for {closure_name}")
                    lua_lines.append(f"{indent}local function callback(...)")
                    closure_info_stack.append("end")

            elif op["type"] == "closure_end":
                if closure_info_stack:
                    close_str = closure_info_stack.pop()
                else:
                    close_str = "end"
                indent_inner = "    " * len(closure_info_stack)
                lua_lines.append(f"{indent_inner}{close_str}")

            elif op["type"] == "loadstring":
                lua_lines.append(f"{indent}-- {op['raw']}")

            i += 1

    output_lines = ["-- Deobfuscated via Trace Emulation", ""]

    if constants_str.strip():
        output_lines.append("-- === String Constants ===")
        output_lines.append(constants_str.strip())
        output_lines.append("")

    output_lines.extend(lua_lines)

    final_output = "\n".join(output_lines)
    final_output = postprocess_output(final_output)

    out_file = report_file.replace(".report.txt", ".deobf.lua")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(final_output)

    print(f"Saved {out_file}")


def process_call_line(raw, var_map, var_counter, used_vars):
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
        a = re.sub(r'function:\s*[0-9a-fA-F]+', 'function(...) end', a)
        clean_arg_strs.append(a)
    args_str = ", ".join(clean_arg_strs)

    if is_method:
        call_expr = f"{obj_str}:{method_str}({args_str})"
    else:
        call_expr = f"{func_chain}({args_str})"

    needs_var = True
    nice_name = None

    if is_method:
        nice_name = generate_var_name(obj_str, method_str, clean_arg_strs)

        if method_str in ("Connect", "FireServer", "Disconnect", "Destroy",
                          "CaptureController", "ClickButton2", "ChangeState",
                          "MoveTo", "SetPrimaryPartCFrame", "ClearAllChildren",
                          "Clone", "Remove", "remove", "insert", "sort"):
            needs_var = False

        if method_str == "wait":
            needs_var = False
    else:
        nice_name = generate_var_name_from_func(func_chain, clean_arg_strs)
        if "task.wait" in func_chain or "wait" in func_chain.lower():
            needs_var = False

    if nice_name and needs_var:
        if nice_name in used_vars:
            count = var_counter.get(nice_name, 1) + 1
            var_counter[nice_name] = count
            final_name = f"{nice_name}{count}"
        else:
            final_name = nice_name
            var_counter[nice_name] = 1

        used_vars.add(final_name)
        var_map[orig_var] = final_name
        return f"local {final_name} = {call_expr}"
    else:
        if nice_name:
            var_map[orig_var] = nice_name
        else:
            var_map[orig_var] = call_expr
        return call_expr


def resolve_vars(text, var_map):
    sorted_vars = sorted(var_map.keys(), key=len, reverse=True)

    for dummy_var in sorted_vars:
        if dummy_var and var_map[dummy_var]:
            clean_var = var_map[dummy_var]
            text = re.sub(r'\b' + re.escape(dummy_var) + r'\b', clean_var, text)

    text = re.sub(r'\b[a-zA-Z0-9_]+_v(\d+)\b', r'v\1', text)

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
    lines = output.split("\n")
    cleaned = []
    prev_line = ""

    for line in lines:
        stripped = line.strip()

        if stripped == "" and prev_line.strip() == "":
            continue

        line = re.sub(r'function:\s*[0-9a-fA-F]{10,}', 'function(...) end', line)

        cleaned.append(line)
        prev_line = line

    return "\n".join(cleaned)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        parse_trace(sys.argv[1])
    else:
        for file in os.listdir("obfuscated_scripts"):
            if file.endswith(".report.txt"):
                parse_trace(os.path.join("obfuscated_scripts", file))
