local messages = {
    "standalone-lua",
    "quotes: \"hello\" and 'world'",
    "path: C:\\fixtures\\sample.lua",
    "first\nsecond\tcolumn\rreturn",
    "Grüße 世界",
    "",
    "\000\001\127\128\255",
    "https://example.com/test?mode=lua&value=42"
}

local function sum(values)
    local result = 0
    for _, value in ipairs(values) do
        result = result + value
    end
    return result
end

for index, message in ipairs(messages) do
    print(index, message)
end

print("numbers", 42, -17, 3.25, true, false, nil, "after-nil")
print("sum", sum({2, 3, 5}))
return "lua-complete", 42, false
