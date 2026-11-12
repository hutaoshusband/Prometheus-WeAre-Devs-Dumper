local total = 0
local message = "standalone-luau"

for index = 1, 4 do
    total += index * 2
end

message ..= ":ready"
print(message, total)
print("literal += stays literal", "brackets [=[text]=]", "\"quoted\",comma")
print("luau\nline\tcolumn", "Grüße 世界", "\000\255", "")
print("values", 4096, -0.125, true, false, nil, "after-nil")
return "luau-complete", total, true
