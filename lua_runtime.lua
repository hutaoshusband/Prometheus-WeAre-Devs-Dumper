local real_type = type
local real_print = print
local real_tostring = tostring
local real_tonumber = tonumber
local real_unpack = unpack
local real_setmetatable = setmetatable
local captured_tables = {}
local constants = {}
local seen_constants = {}
local trace_count = 0
local call_count = 0
local wait_count = 0
local closure_failure = false
local callback_count = 0
local proxy_values = {}

local function emit(message)
    trace_count = trace_count + 1
    if trace_count > 10000 then
        error("trace limit reached", 0)
    end
    real_print(message)
end

local function quote(value)
    local parts = {'"'}
    for index = 1, #value do
        local byte = string.byte(value, index)
        if byte == 34 then
            parts[#parts + 1] = '\\"'
        elseif byte == 92 then
            parts[#parts + 1] = "\\\\"
        elseif byte == 10 then
            parts[#parts + 1] = "\\n"
        elseif byte == 13 then
            parts[#parts + 1] = "\\r"
        elseif byte == 9 then
            parts[#parts + 1] = "\\t"
        elseif byte >= 32 and byte <= 126 then
            parts[#parts + 1] = string.char(byte)
        else
            parts[#parts + 1] = string.format("\\%03d", byte)
        end
    end
    parts[#parts + 1] = '"'
    return table.concat(parts)
end

local function is_dummy(value)
    local meta = getmetatable(value)
    return real_type(meta) == "table" and rawget(meta, "__is_mock_dummy") == true
end

local function serialize(value, depth, visited)
    local kind = real_type(value)
    if kind == "string" then
        return quote(value)
    elseif kind == "number" then
        if value ~= value then return "(0/0)" end
        if value == math.huge then return "math.huge" end
        if value == -math.huge then return "-math.huge" end
        return string.format("%.17g", value)
    elseif kind == "boolean" or kind == "nil" then
        return real_tostring(value)
    elseif is_dummy(value) then
        return real_tostring(value)
    elseif kind == "function" then
        return "function(...) end"
    elseif kind == "table" then
        depth = depth or 0
        visited = visited or {}
        if depth > 4 or visited[value] then return "{}" end
        visited[value] = true
        local parts = {}
        for key, item in pairs(value) do
            if real_type(key) == "string" or real_type(key) == "number" then
                parts[#parts + 1] = "[" .. serialize(key) .. "] = " .. serialize(item, depth + 1, visited)
            end
        end
        table.sort(parts)
        visited[value] = nil
        return "{" .. table.concat(parts, ", ") .. "}"
    end
    return "nil"
end

local function capture(value)
    local kind = real_type(value)
    if kind ~= "string" and kind ~= "number" and kind ~= "boolean" then return end
    local literal = serialize(value)
    local key = kind .. ":" .. literal
    if not seen_constants[key] then
        seen_constants[key] = true
        constants[#constants + 1] = literal
    end
end

local function capture_table(value)
    captured_tables[#captured_tables + 1] = value
    return value
end

local function arguments(...)
    local parts = {}
    for index = 1, select("#", ...) do
        local value = select(index, ...)
        capture(value)
        parts[index] = serialize(value)
    end
    return table.concat(parts, ", ")
end

local create_dummy

create_dummy = function(name)
    local dummy = {}
    local properties = {}
    return real_setmetatable(dummy, {
        __is_mock_dummy = true,
        __index = function(_, key)
            capture(key)
            if properties[key] ~= nil then return properties[key] end
            local field = real_type(key) == "string" and key:match("^[%a_][%w_]*$")
                and ("." .. key) or ("[" .. serialize(key) .. "]")
            local result = create_dummy(name .. field)
            properties[key] = result
            emit("ACCESSED --> " .. name .. field)
            return result
        end,
        __newindex = function(_, key, value)
            capture(key)
            capture(value)
            properties[key] = value
            local field = real_type(key) == "string" and key:match("^[%a_][%w_]*$")
                and ("." .. key) or ("[" .. serialize(key) .. "]")
            emit("PROP_SET --> " .. name .. field .. " = " .. serialize(value))
        end,
        __call = function(_, ...)
            call_count = call_count + 1
            local variable = "trace_" .. call_count
            emit("CALL_RESULT --> local " .. variable .. " = " .. name .. "(" .. arguments(...) .. ")")
            local callbacks = 0
            for index = 1, select("#", ...) do
                if real_type((select(index, ...))) == "function" then callbacks = callbacks + 1 end
            end
            if callbacks > 1 then error("multiple callback arguments are unsupported", 0) end
            if name == "wait" or name == "task.wait" then
                wait_count = wait_count + 1
                if wait_count > 10 then error("wait limit reached", 0) end
                return 0
            end
            for index = 1, select("#", ...) do
                local value = select(index, ...)
                if real_type(value) == "function" then
                    callback_count = callback_count + 1
                    local names = {}
                    for argument = 1, 4 do
                        names[argument] = "callback" .. callback_count .. "_arg" .. argument
                    end
                    emit("--- ENTERING CLOSURE FOR " .. name .. " ---")
                    emit("CLOSURE_ARGS --> " .. table.concat(names, ", "))
                    local success, message = pcall(value, create_dummy(names[1]), create_dummy(names[2]),
                        create_dummy(names[3]), create_dummy(names[4]))
                    if not success then
                        closure_failure = true
                        emit("CLOSURE ERROR --> " .. quote(real_tostring(message)))
                    end
                    emit("--- EXITING CLOSURE FOR " .. name .. " ---")
                end
            end
            if name:match("%.HttpGetAsync?$") or name:match("%.HttpGet$") then
                return ""
            end
            if name == "readfile" then return "" end
            if name == "isfile" or name == "isfolder" then return false end
            if name == "listfiles" then return {} end
            return create_dummy(variable)
        end,
        __tostring = function() return name end,
        __concat = function(left, right) return real_tostring(left) .. real_tostring(right) end,
        __add = function(left, right) return create_dummy("(" .. real_tostring(left) .. "+" .. real_tostring(right) .. ")") end,
        __sub = function(left, right) return create_dummy("(" .. real_tostring(left) .. "-" .. real_tostring(right) .. ")") end,
        __mul = function(left, right) return create_dummy("(" .. real_tostring(left) .. "*" .. real_tostring(right) .. ")") end,
        __div = function(left, right) return create_dummy("(" .. real_tostring(left) .. "/" .. real_tostring(right) .. ")") end,
        __mod = function() return 0 end,
        __pow = function() return 0 end,
        __unm = function() return 0 end,
        __lt = function() return false end,
        __le = function() return false end,
        __eq = function(left, right) return rawequal(left, right) end,
        __len = function() return 1 end,
    })
end

local function mock_iterator(iterator, value)
    if proxy_values[value] then return iterator(proxy_values[value]) end
    if not is_dummy(value) then return iterator(value) end
    local done = false
    return function()
        if done then return nil end
        done = true
        return 1, create_dummy(real_tostring(value) .. "_v1")
    end
end

local safe_string = {}
for key, value in pairs(string) do safe_string[key] = value end
safe_string.char = function(...)
    local values = {}
    for index = 1, select("#", ...) do
        local value = select(index, ...)
        values[index] = is_dummy(value) and 1 or value
    end
    return string.char(real_unpack(values, 1, select("#", ...)))
end

local safe_table = {}
for key, value in pairs(table) do safe_table[key] = value end
safe_table.unpack = real_unpack
safe_table.concat = function(...)
    local result = table.concat(...)
    capture(result)
    if result:match("https?://") or result:match("www%.") then
        emit("URL DETECTED IN CONCAT --> " .. result:gsub("\r", "\\r"):gsub("\n", "\\n"))
    end
    return result
end

local environment = {}
local global_values = {}
local assigned_globals = {}
proxy_values[environment] = global_values
local safe_globals = {
    string = safe_string,
    table = safe_table,
    math = math,
    coroutine = coroutine,
    select = select,
    unpack = real_unpack,
    tonumber = function(value, base)
        if is_dummy(value) then return 1 end
        return real_tonumber(value, base)
    end,
    tostring = real_tostring,
    type = function(value)
        return is_dummy(value) and "userdata" or real_type(value)
    end,
    typeof = function(value)
        return is_dummy(value) and "Instance" or real_type(value)
    end,
    pairs = function(value) return mock_iterator(pairs, value) end,
    ipairs = function(value) return mock_iterator(ipairs, value) end,
    pcall = pcall,
    xpcall = xpcall,
    getfenv = function() return environment end,
    setfenv = function(callback) return setfenv(callback, environment) end,
    getmetatable = getmetatable,
    setmetatable = function(value, meta)
        if real_type(meta) == "table" and real_type(meta.__index) == "table" then
            capture_table(meta.__index)
        end
        return real_setmetatable(value, meta)
    end,
    newproxy = newproxy,
    assert = assert,
    error = error,
    next = function(value, key) return next(proxy_values[value] or value, key) end,
    rawget = rawget,
    rawset = rawset,
    rawequal = rawequal,
    _VERSION = _VERSION,
    __capture_table = capture_table,
    print = function(...) emit("PRINT_CALL --> print(" .. arguments(...) .. ")") end,
    warn = function(...) emit("PRINT_CALL --> warn(" .. arguments(...) .. ")") end,
}

local mock_names = {}
for name in ("game workspace Workspace Instance Enum Vector2 Vector3 CFrame UDim UDim2 Color3 " ..
    "BrickColor Ray NumberRange NumberSequence ColorSequence task wait spawn delay tick time elapsedTime " ..
    "getgc getinstances getnilinstances getloadedmodules getconnections firesignal fireclickdetector " ..
    "firetouchinterest isnetworkowner gethiddenproperty sethiddenproperty setsimulationradius " ..
    "rconsoleprint rconsolewarn rconsoleerr rconsoleinfo rconsolename rconsoleclear consoleprint consolewarn " ..
    "clonefunction hookfunction newcclosure replaceclosure restoreclosure islclosure iscclosure checkcaller " ..
    "getnamecallmethod setnamecallmethod getrawmetatable setrawmetatable setreadonly isreadonly " ..
    "iswindowactive keypress keyrelease mouse1click mouse1press mouse1release mousescroll mousemoverel " ..
    "mousemoveabs hookmetamethod getcallingscript makefolder writefile readfile appendfile listfiles " ..
    "isfile isfolder delfile delfolder request http_request"):gmatch("%S+") do
    mock_names[name] = true
end

real_setmetatable(environment, {
    __index = function(target, key)
        if assigned_globals[key] then return global_values[key] end
        if safe_globals[key] ~= nil then return safe_globals[key] end
        if mock_names[key] then
            if global_values[key] ~= nil then return global_values[key] end
            local value = create_dummy(key)
            global_values[key] = value
            emit("ACCESSED --> " .. key)
            return value
        end
        return nil
    end,
    __newindex = function(target, key, value)
        capture(value)
        local assignment = real_type(key) == "string" and key:match("^[%a_][%w_]*$")
            and key or ("_G[" .. serialize(key) .. "]")
        emit("SET GLOBAL --> " .. assignment .. " = " .. serialize(value))
        assigned_globals[key] = true
        global_values[key] = value
    end,
})

safe_globals._G = environment
safe_globals._ENV = environment
safe_globals.rawget = function(target, key)
    return rawget(proxy_values[target] or target, key)
end
safe_globals.rawset = function(target, key, value)
    if proxy_values[target] then
        target[key] = value
    else
        rawset(target, key, value)
    end
    return target
end
local shared_values = {}
safe_globals.shared = real_setmetatable({}, {
    __index = shared_values,
    __newindex = function(_, key, value)
        capture(key)
        capture(value)
        shared_values[key] = value
        emit("PROP_SET --> shared[" .. serialize(key) .. "] = " .. serialize(value))
    end,
})
proxy_values[safe_globals.shared] = shared_values
safe_globals.getgenv = function() return environment end
safe_globals.getrenv = safe_globals.getgenv
safe_globals.loadstring = function(source)
    capture(source)
    emit("LOADSTRING --> " .. quote(source))
    local chunk, message = loadstring(source)
    if chunk then setfenv(chunk, environment) end
    return chunk, message
end
safe_globals.load = safe_globals.loadstring

if jit then jit.off() end
local instructions = 0
debug.sethook(function()
    instructions = instructions + 10000
    if instructions > 20000000 then error("instruction limit reached", 0) end
end, "", 10000)

local chunk, message = loadfile(arg[1])
local success = false
if chunk then
    setfenv(chunk, environment)
    local function finish(ok, ...)
        success = ok
        if ok then
            if select("#", ...) > 0 then emit("RETURN --> return " .. arguments(...)) end
        else
            emit("RUNTIME ERROR --> " .. quote(real_tostring((...))))
        end
    end
    finish(pcall(chunk))
else
    emit("COMPILE ERROR --> " .. quote(message))
end
debug.sethook()

for _, values in ipairs(captured_tables) do
    local keys = {}
    for key in pairs(values) do
        if real_type(key) == "number" or real_type(key) == "string" then keys[#keys + 1] = key end
    end
    table.sort(keys, function(left, right)
        if real_type(left) == real_type(right) then return left < right end
        return real_type(left) < real_type(right)
    end)
    for _, key in ipairs(keys) do capture(values[key]) end
end

real_print("--- CONSTANTS START ---")
local entries = {}
for index, value in ipairs(constants) do
    entries[index] = "[" .. index .. "] = " .. value
end
real_print("local Constants = {\n    " .. table.concat(entries, ",\n    ") .. "\n}")
real_print("--- CONSTANTS END ---")
if not success or closure_failure then os.exit(1) end
