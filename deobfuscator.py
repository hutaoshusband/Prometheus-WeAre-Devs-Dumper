import re
import sys
import subprocess
import time
import os
import glob
import math

def deobfuscate_file(filepath):
    print(f"Processing {filepath}...")
    
    if ".deobf." in filepath or ".report." in filepath:
        return
        
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return

    match = re.search(r'local ([a-zA-Z0-9_]+)=\{"', content)
    if not match:
        print(f"Could not identify string table variable in {filepath}.")
        return
    var_name = match.group(1)

    mock_env_code = r"""
local real_type = type
local real_tonumber = tonumber
local real_unpack = unpack
local real_concat = table.concat
local real_tostring = tostring
local real_print = print

local _LOOP_COUNTER = 0
local _MAX_LOOPS = 150
local _LOOP_BODIES = {}

local function _check_loop()
    _LOOP_COUNTER = _LOOP_COUNTER + 1
    if _LOOP_COUNTER > _MAX_LOOPS then
        return false
    end
    return true
end

local function type(v)
    local mt = getmetatable(v)
    if mt and mt.__is_mock_dummy then
        return "userdata"
    end
    return real_type(v)
end

local function typeof(v)
    local mt = getmetatable(v)
    if mt and mt.__is_mock_dummy then
        return "Instance"
    end
    return type(v)
end

local function tonumber(v, base)
    if type(v) == "userdata" or (type(v) == "table" and getmetatable(v) and getmetatable(v).__is_mock_dummy) then
        return 1
    end
    return real_tonumber(v, base)
end

local function unpack(t, i, j)
    if real_type(t) == "table" then
        local looks_like_chunk = true
        for k, v in pairs(t) do
            if real_type(k) ~= "number" then looks_like_chunk = false break end
        end
        
        if looks_like_chunk and #t > 0 then
            print("UNPACK CALLED WITH TABLE (Potential Chunk): size=" .. #t)
            local success, res = pcall(real_concat, t, ",")
            if success then
                print("CAPTURED CHUNK STRING: " .. res)
                if res:match("http") or res:match("www") then
                    print("URL DETECTED IN UNPACK --> " .. res:match("https?://[%w%.%-%/]+"))
                end
            end
        end
    end
    return real_unpack(t, i, j)
end

local function table_concat(t, sep, i, j)
    local res = real_concat(t, sep, i, j)
    if real_type(res) == "string" and (res:match("http") or res:match("www")) then
         print("URL DETECTED IN CONCAT --> " .. res:match("https?://[%w%.%-%/]+"))
    end
    return res
end

local function recursive_tostring(v, depth)
    if depth == nil then depth = 0 end
    if depth > 2 then return tostring(v) end
    
    if real_type(v) == "string" then
        return '"' .. v .. '"'
    elseif real_type(v) == "number" then
        if v == math.floor(v) and v >= -2147483648 and v <= 2147483647 then
            return tostring(math.floor(v))
        end
        return tostring(v)
    elseif real_type(v) == "boolean" then
        return tostring(v)
    elseif v == nil then
        return "nil"
    elseif real_type(v) == "table" then
        if getmetatable(v) and getmetatable(v).__is_mock_dummy then
            return tostring(v)
        end
        local parts = {}
        local keys = {}
        for k in pairs(v) do table.insert(keys, k) end
        table.sort(keys, function(a,b) return tostring(a) < tostring(b) end)

        for _, k in ipairs(keys) do
            local val = v[k]
            local k_str = tostring(k)
            if real_type(k) == "string" then k_str = '["' .. k .. '"]' end
            table.insert(parts, k_str .. " = " .. recursive_tostring(val, depth + 1))
        end
        return "{" .. real_concat(parts, ", ") .. "}"
    elseif real_type(v) == "function" then
        return tostring(v)
    else
        return tostring(v)
    end
end

local function create_dummy(name)
    local d = {}
    local mt = {
        __is_mock_dummy = true,
        __index = function(_, k)
             print("ACCESSED --> " .. name .. "." .. k)
             if k == "HttpGet" or k == "HttpGetAsync" then
                 return function(_, url, ...)
                     print("URL DETECTED --> " .. tostring(url))
                     return create_dummy("HttpGetResult")
                 end
            end
            return create_dummy(name .. "." .. k)
        end,
        __newindex = function(_, k, v)
            local val_str = recursive_tostring(v, 0)
            print("PROP_SET --> " .. name .. "." .. k .. " = " .. val_str)
        end,
        __call = function(_, ...)
            local args = {...}
            local arg_str = ""
            for i, v in ipairs(args) do
                if i > 1 then arg_str = arg_str .. ", " end
                arg_str = arg_str .. recursive_tostring(v)
            end

            local var_name = name:gsub("%.", "_") .. "_" .. math.random(100, 999)
            print("CALL_RESULT --> local " .. var_name .. " = " .. name .. "(" .. arg_str .. ")")
            
            for i, v in ipairs(args) do
                if real_type(v) == "function" then
                    print("--- ENTERING CLOSURE FOR " .. name .. " ---")
                    local success, err = pcall(v, 
                        create_dummy("arg1"), create_dummy("arg2"), 
                        create_dummy("arg3"), create_dummy("arg4"))
                    if not success then 
                        print("-- CLOSURE ERROR: " .. tostring(err)) 
                    end
                    print("--- EXITING CLOSURE FOR " .. name .. " ---")
                end
            end
            
            return create_dummy(var_name)
        end,
        __tostring = function() return name end,
        __concat = function(a, b) return tostring(a) .. tostring(b) end,
        __add = function(a, b) return create_dummy("("..tostring(a).."+"..tostring(b)..")") end,
        __sub = function(a, b) return create_dummy("("..tostring(a).."-"..tostring(b)..")") end,
        __mul = function(a, b) return create_dummy("("..tostring(a).."*"..tostring(b)..")") end,
        __div = function(a, b) return create_dummy("("..tostring(a).."/"..tostring(b)..")") end,
        __mod = function(a, b) return create_dummy("("..tostring(a).."%"..tostring(b)..")") end,
        __pow = function(a, b) return create_dummy("("..tostring(a).."^"..tostring(b)..")") end,
        __unm = function(a) return create_dummy("-"..tostring(a)) end,
        __lt = function(a, b) return false end,
        __le = function(a, b) return false end,
        __eq = function(a, b) return false end,
        __len = function(a) return 2 end,
    }
    setmetatable(d, mt)
    return d
end

local function mock_pairs(t)
    local mt = getmetatable(t)
    if mt and mt.__is_mock_dummy then
        local i = 0
        return function(...)
            i = i + 1
            if i <= 1 then
                return i, create_dummy(tostring(t).."_v"..i)
            end
            return nil
        end
    end
    return pairs(t)
end

local function mock_ipairs(t)
    local mt = getmetatable(t)
    if mt and mt.__is_mock_dummy then
        local i = 0
        return function(...)
            i = i + 1
            if i <= 1 then
                return i, create_dummy(tostring(t).."_v"..i)
            end
            return nil
        end
    end
    return ipairs(t)
end

local MockEnv = {}
local safe_globals = {
    ["string"] = string,
    ["table"] = {
        ["insert"] = table.insert,
        ["remove"] = table.remove,
        ["sort"] = table.sort,
        ["concat"] = table_concat,
        ["maxn"] = table.maxn
    },
    ["math"] = math,
    ["pairs"] = mock_pairs,
    ["ipairs"] = mock_ipairs,
    ["select"] = select,
    ["unpack"] = unpack,
    ["tonumber"] = tonumber,
    ["tostring"] = tostring,
    ["type"] = type,
    ["typeof"] = typeof,
    ["pcall"] = pcall,
    ["xpcall"] = xpcall,
    ["getfenv"] = getfenv,
    ["setmetatable"] = setmetatable,
    ["getmetatable"] = getmetatable,
    ["error"] = error,
    ["assert"] = assert,
    ["next"] = next,
    ["print"] = function(...)
        local args = {...}
        local parts = {}
        for i,v in ipairs(args) do table.insert(parts, tostring(v)) end
        print("TRACE_PRINT --> " .. table.concat(parts, "\t"))
    end,
    ["_VERSION"] = _VERSION,
    ["rawset"] = rawset,
    ["rawget"] = rawget,
    ["os"] = os,
    ["io"] = io,
    ["package"] = package,
    ["debug"] = debug,
    ["dofile"] = dofile,
    ["loadfile"] = loadfile,
    ["loadstring"] = function(s) 
        print("LOADSTRING DETECTED: size=" .. tostring(#s)) 
        print("LOADSTRING CONTENT START")
        print(s)
        print("LOADSTRING CONTENT END")
        return function() print("DUMMY FUNC CALLED") end
    end
}

setmetatable(MockEnv, {
    __index = function(t, k)
        if safe_globals[k] then
            return safe_globals[k]
        end

        if k == "game" then
            print("ACCESSED --> game")
            return create_dummy("game")
        end
        if k == "getgenv" or k == "getrenv" or k == "getreg" then
            return function() return MockEnv end
        end

        local exploit_funcs = {
            "getgc", "getinstances", "getnilinstances",
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
            "delfolder", "dofile", "bit", "bit32", 
            "Vector2", "Vector3", "CFrame", "UDim2", "Color3", "Instance", "Ray",
            "Enum", "BrickColor", "NumberRange", "NumberSequence", "ColorSequence",
            "task", "coroutine", "Delay", "delay", "Spawn", "spawn", "Wait", "wait", 
            "workspace", "Workspace", "tick", "time", "elapsedTime", "utf8"
        }
        for _, name in ipairs(exploit_funcs) do
            if k == name then
                print("ACCESSED --> " .. k)
                return create_dummy(k)
            end
        end

        -- 4. Fallback: Return NIL (to satisfy Fallback Path logic)
        print("ACCESSED (NIL) --> " .. k)
        return nil
    end,
    
    __newindex = function(t, k, v)
        local val_str = ""
        if real_type(v) == "string" then
            val_str = '"' .. v .. '"'
        elseif real_type(v) == "number" or real_type(v) == "boolean" then
            val_str = tostring(v)
        else
            val_str = tostring(v)
        end
        print("SET GLOBAL --> " .. tostring(k) .. " = " .. val_str)
        rawset(t, k, v)
    end
})

safe_globals["_G"] = MockEnv
safe_globals["shared"] = MockEnv
"""

    idx_args = content.rfind("(getfenv")
    if idx_args == -1:
         idx_args = content.rfind("( getfenv")

    if idx_args == -1:
         idx_args = len(content)

    idx_ret = content.rfind("return(function", 0, idx_args)
    if idx_ret == -1:
        print(f"Could not find return(function injection point in {filepath}.")
        return

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

    if "getfenv and getfenv()or _ENV" in new_content:
        new_content = new_content.replace("getfenv and getfenv()or _ENV", "MockEnv")
    else:
        new_content = re.sub(r'getfenv\s+and\s+getfenv\(\)or\s+_ENV', 'MockEnv', new_content)

    temp_file = "temp_deob.lua"
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"Executing deobfuscation for {filepath}...")

    process = subprocess.Popen(["lua_bin/lua5.1.exe", temp_file, "1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stdout_lines = []
    
    RELEVANT_PREFIXES = (
        "ACCESSED", "CALL_RESULT", "local Constants =", 
        "URL DETECTED", "SET GLOBAL", "UNPACK CALLED", 
        "CAPTURED CHUNK", "CLOSURE", "TRACE_PRINT", 
        "PROP_SET", "LOADSTRING"
    )
    
    start_time = time.time()
    try:
        while True:
            if process.poll() is not None:
                break
            line = process.stdout.readline()
            if line:
                decoded_line = line.decode('utf-8', errors='replace').strip()
                stdout_lines.append(decoded_line)
                if any(prefix in decoded_line for prefix in RELEVANT_PREFIXES):
                    print(decoded_line)

            if time.time() - start_time > 20:
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
            if any(prefix in line for prefix in RELEVANT_PREFIXES):
                print(line.strip())
    if err:
        stderr_text = err.decode('utf-8', errors='replace')
        if stderr_text.strip():
            print("STDERR:", stderr_text)

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
        elif any(prefix in line for prefix in RELEVANT_PREFIXES):
            trace_lines.append(line)

    report_file = filepath + ".report.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("--- DEOBFUSCATION REPORT ---\n")
        f.write(f"File: {filepath}\n\n")
        f.write("--- TRACE ---\n")
        for line in trace_lines:
            f.write(line + "\n")
        f.write("\n--- CONSTANTS ---\n")
        f.write(constants_str)

    print(f"Report saved to {report_file}")

    try:
        import trace_to_lua
        import importlib
        importlib.reload(trace_to_lua)
        trace_to_lua.parse_trace(report_file)
    except Exception as e:
        print(f"Failed to convert trace: {e}")
        import traceback
        traceback.print_exc()

    if os.path.exists(temp_file):
        os.remove(temp_file)
    #if os.path.exists(report_file):
    #    os.remove(report_file)

def main():
    target = "obfuscated_scripts"
    if len(sys.argv) > 1:
        target = sys.argv[1]

    if os.path.isfile(target):
        deobfuscate_file(target)
    elif os.path.isdir(target):
        files = glob.glob(os.path.join(target, "*.lua"))
        for file in sorted(files):
            if "temp_deob" in file or ".report.txt" in file or ".deobf." in file:
                continue
            deobfuscate_file(file)
            print("-" * 40)
    else:
        print("Invalid path")

if __name__ == "__main__":
    main()


def main():
    target = "obfuscated_scripts"
    if len(sys.argv) > 1:
        target = sys.argv[1]

    if os.path.isfile(target):
        deobfuscate_file(target)
    elif os.path.isdir(target):
        files = glob.glob(os.path.join(target, "*.lua"))
        for file in sorted(files):
            if "temp_deob" in file or ".report.txt" in file or ".deobf." in file:
                continue
            deobfuscate_file(file)
            print("-" * 40)
    else:
        print("Invalid path")

if __name__ == "__main__":
    main()
