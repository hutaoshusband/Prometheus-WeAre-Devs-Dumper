local players = game:GetService("Players")
local storage = game:GetService("ReplicatedStorage")
local remote = storage:WaitForChild("FixtureRemote")
local folder = Instance.new("Folder")

folder.Name = "RobloxLuaFixture"
folder.Parent = workspace
folder:SetAttribute("FixtureCount", 42)
folder:SetAttribute("Enabled", true)

local function greet(player)
    remote:FireServer("hello-player", player, 3.25, false)
    print("callback-lua", "quotes: \"yes\"", "\000\255")
end

players.PlayerAdded:Connect(greet)
print("roblox-lua", "Grüße 世界", "line\nnext", "", 42, -17, true, false)
return "roblox-lua-complete"
