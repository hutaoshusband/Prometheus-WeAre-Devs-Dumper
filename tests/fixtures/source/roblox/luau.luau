local storage = game:GetService("ReplicatedStorage")
local remote = storage:WaitForChild("LuauFixtureRemote")
local part = Instance.new("Part")
local count = 2

count *= 4
part.Name = "RobloxLuauFixture"
part.Anchored = true
part.Transparency = 0.25
part.Position = Vector3.new(1, 2, 3)
part.Parent = workspace
part:SetAttribute("Count", count)

remote.OnClientEvent:Connect(function(value)
    print("callback-luau", value, "escaped\\path", "\000\255")
end)

remote:FireServer("fixture-ready", count, false)
print("roblox-luau", "Grüße 世界", "line\nnext", "", 4096, -0.125, true, false)
return "roblox-luau-complete"
