import re
import sys
import subprocess
import time
import os
import glob
import math

def deobfuscate_file(filepath):
    print(f"Processing {filepath}...")
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return

    # 1. Identify Variable Name for String Table
    # Usually: local f={"..."} or local D={"..."} at the start
    match = re.search(r'local ([a-zA-Z0-9_]+)=\{"', content)
    if not match:
        print(f"Could not identify string table variable in {filepath}.")
        return
    var_name = match.group(1)

    # 2. Prepare Mock Environment Code
    # We blacklist dangerous libraries for security.
    mock_env_code = r"""
-- Security: Disable dangerous libraries
os = nil
io = nil
package = nil
debug = nil
dofile = nil
loadfile = nil

local function create_dummy(name)
    local d = {}
    local mt = {
        __index = function(_, k)
            -- print("ACCESSED --> " .. name .. "." .. k)
            return create_dummy(name .. "." .. k)
        end,
        __call = function(_, ...)
            local args = {...}
            local arg_str = ""
            for i, v in ipairs(args) do
                if i > 1 then arg_str = arg_str .. ", " end
                if type(v) == "string" then
                    arg_str = arg_str .. '"' .. v .. '"'
                elseif type(v) == "table" then
                     arg_str = arg_str .. tostring(v)
                else
                    arg_str = arg_str .. tostring(v)
                end
            end

            -- Log the call result as requested
            local var_name = name:gsub("%.", "_") .. "_" .. math.random(100, 999)
            print("CALL_RESULT --> local " .. var_name .. " = " .. name .. "(" .. arg_str .. ")")

            if name == "loadstring" or name:match("%.loadstring$") then
                 return create_dummy("loadstring_result")
            end

            return create_dummy(var_name)
        end,
        __tostring = function() return name end,
        __concat = function(a, b) return tostring(a) .. tostring(b) end,

        -- Arithmetic metamethods to prevent 'attempt to perform arithmetic' errors
        -- We return dummy objects for results, which also have these metamethods.
        -- We use a dummy string representation.
        __add = function(a, b) return create_dummy("("..tostring(a).."+"..tostring(b)..")") end,
        __sub = function(a, b) return create_dummy("("..tostring(a).."-"..tostring(b)..")") end,
        __mul = function(a, b) return create_dummy("("..tostring(a).."*"..tostring(b)..")") end,
        __div = function(a, b) return create_dummy("("..tostring(a).."/"..tostring(b)..")") end,
        __mod = function(a, b) return create_dummy("("..tostring(a).."%"..tostring(b)..")") end,
        __pow = function(a, b) return create_dummy("("..tostring(a).."^"..tostring(b)..")") end,
        __unm = function(a) return create_dummy("-"..tostring(a)) end,

        -- Logic metamethods
        -- We return false to likely terminate loops that rely on < or <=
        __lt = function(a, b) return false end,
        __le = function(a, b) return false end,
        __eq = function(a, b) return false end,

        __len = function(a) return 0 end,
    }
    setmetatable(d, mt)
    return d
end

local MockEnv = {}
local safe_globals = {
    ["string"] = string,
    ["table"] = table,
    ["math"] = math,
    ["pairs"] = pairs,
    ["ipairs"] = ipairs,
    ["select"] = select,
    ["unpack"] = unpack,
    ["tonumber"] = tonumber,
    ["tostring"] = tostring,
    ["type"] = type,
    ["pcall"] = pcall,
    ["xpcall"] = xpcall,
    ["getfenv"] = getfenv,
    ["setmetatable"] = setmetatable,
    ["getmetatable"] = getmetatable,
    ["error"] = error,
    ["assert"] = assert,
    ["next"] = next,
    ["print"] = print, -- allow print for debugging, but we capture stdout so it's fine
    ["_G"] = _G, -- _G is needed but we should ensure it doesn't contain unsafe stuff
    ["_VERSION"] = _VERSION
}

-- Ensure _G in safe_globals is cleaned
for k, v in pairs(_G) do
    if not safe_globals[k] and k ~= "loaded" then -- Keep standard lua stuff?
       -- Actually, we better just return safe_globals[k] if exists
    end
end

setmetatable(MockEnv, {
    __index = function(t, k)
        if k == "game" then
            print("ACCESSED --> game")
            return create_dummy("game")
        end
        if k == "loadstring" then
            print("ACCESSED --> loadstring")
            return create_dummy("loadstring")
        end
        if k == "script" then return create_dummy("script") end

        -- Check safe globals
        if safe_globals[k] then
            return safe_globals[k]
        end

        -- Exploit environment mocks
        local exploit_funcs = {
            "getgenv", "getrenv", "getreg", "getgc", "getinstances", "getnilinstances",
            "getloadedmodules", "getconnections", "firesignal", "fireclickdetector",
            "firetouchinterest", "isnetworkowner", "gethiddenproperty", "sethiddenproperty",
            "setsimulationradius", "rconsoleprint", "rconsolewarn", "rconsoleerr",
            "rconsoleinfo", "rconsolename", "rconsoleclear", "consoleprint", "consolewarn",
            "consoleerr", "consoleinfo", "consolename", "consoleclear", "warn", "print",
            "error", "debug", "clonefunction", "hookfunction", "newcclosure", "replaceclosure",
            "restoreclosure", "islclosure", "iscclosure", "checkcaller", "getnamecallmethod",
            "setnamecallmethod", "getrawmetatable", "setrawmetatable", "setreadonly",
            "isreadonly", "iswindowactive", "keypress", "keyrelease", "mouse1click",
            "mouse1press", "mouse1release", "mousescroll", "mousemoverel", "mousemoveabs",
            "hookmetamethod", "getcallingscript", "makefolder", "writefile", "readfile",
            "appendfile", "loadfile", "listfiles", "isfile", "isfolder", "delfile",
            "delfolder", "dofile", "bit", "bit32"
        }
        for _, name in ipairs(exploit_funcs) do
            if k == name then
                print("ACCESSED --> " .. k)
                return create_dummy(k)
            end
        end

        print("ACCESSED --> " .. k)
        return create_dummy(k)
    end
})
"""

    # 3. Find Injection Point
    # Look for the last 'return(function' before the argument list that contains 'getfenv'
    idx_args = content.rfind("(getfenv")
    if idx_args == -1:
         idx_args = content.rfind("( getfenv")

    if idx_args == -1:
         # Fallback to end
         idx_args = len(content)

    idx_ret = content.rfind("return(function", 0, idx_args)
    if idx_ret == -1:
        print(f"Could not find return(function injection point in {filepath}.")
        return

    # Dumper Code
    dumper_code = f"""
    print("--- CONSTANTS START ---")
    if {var_name} then
        local sorted_keys = {{}}
        for k in pairs({var_name}) do table.insert(sorted_keys, k) end
        table.sort(sorted_keys)
        local out = "local Constants = {{"
        for i, k in ipairs(sorted_keys) do
            local v = {var_name}[k]
            local v_str = tostring(v)
            v_str = string.format("%q", v)
            out = out .. " [" .. k .. "] = " .. v_str .. ","
        end
        out = out .. " }}"
        print(out)
    end
    print("--- CONSTANTS END ---")
    """

    new_content = mock_env_code + content[:idx_ret] + dumper_code + content[idx_ret:]

    # Replace the argument
    if "getfenv and getfenv()or _ENV" in new_content:
        new_content = new_content.replace("getfenv and getfenv()or _ENV", "MockEnv")
    else:
        new_content = re.sub(r'getfenv\s+and\s+getfenv\(\)or\s+_ENV', 'MockEnv', new_content)

    temp_file = "temp_deob.lua"
    with open(temp_file, 'w') as f:
        f.write(new_content)

    print(f"Executing deobfuscation for {filepath}...")

    # Pass a dummy argument '1' to satisfy 'unpack(args)' logic if any
    process = subprocess.Popen(["lua5.1", temp_file, "1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stdout_lines = []
    stderr_lines = []

    start_time = time.time()
    try:
        while True:
            if process.poll() is not None:
                break
            line = process.stdout.readline()
            if line:
                decoded_line = line.decode('utf-8', errors='replace').strip()
                stdout_lines.append(decoded_line)
                # Print progress to console sparingly or all?
                # Let's print just logs and constants to stdout for the user to see progress
                if "ACCESSED -->" in decoded_line or "CALL_RESULT -->" in decoded_line or "local Constants =" in decoded_line:
                    print(decoded_line)

            if time.time() - start_time > 10: # 10 seconds timeout per script
                print("Timeout reached.")
                process.terminate()
                break
    except Exception as e:
        print(f"Error: {e}")
        process.kill()

    out, err = process.communicate()
    if out:
        for line in out.decode('utf-8', errors='replace').splitlines():
            stdout_lines.append(line.strip())
            if "ACCESSED -->" in line or "CALL_RESULT -->" in line or "local Constants =" in line:
                print(line.strip())
    if err:
        stderr_lines.append(err.decode('utf-8', errors='replace'))
        print("STDERR:", err.decode('utf-8', errors='replace'))

    # Process and save report
    constants_str = ""
    trace_lines = []

    in_constants = False
    for line in stdout_lines:
        if line == "--- CONSTANTS START ---":
            in_constants = True
            continue
        if line == "--- CONSTANTS END ---":
            in_constants = False
            continue

        if in_constants:
            constants_str += line + "\n"
        elif "ACCESSED -->" in line or "CALL_RESULT -->" in line:
            trace_lines.append(line)

    report_file = filepath + ".report.txt"
    with open(report_file, 'w') as f:
        f.write("--- DEOBFUSCATION REPORT ---\n")
        f.write(f"File: {filepath}\n\n")
        f.write("--- TRACE ---\n")
        for line in trace_lines:
            f.write(line + "\n")
        f.write("\n--- CONSTANTS ---\n")
        f.write(constants_str)

    print(f"Report saved to {report_file}")

    # Clean up
    if os.path.exists(temp_file):
        os.remove(temp_file)

def main():
    target = "obfuscated_scripts"
    if len(sys.argv) > 1:
        target = sys.argv[1]

    if os.path.isfile(target):
        deobfuscate_file(target)
    elif os.path.isdir(target):
        # Recursive search
        files = glob.glob(os.path.join(target, "**/*.lua"), recursive=True)
        for file in files:
            if "temp_deob" in file or ".report.txt" in file:
                continue
            deobfuscate_file(file)
            print("-" * 40)
    else:
        print("Invalid path")

if __name__ == "__main__":
    main()
