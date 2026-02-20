local players = game:GetService("Players")
local localPlayer = players.LocalPlayer

local function createESP(player)
    local function applyESP(char)
        if not char:FindFirstChild("Highlight") then
            local highlight = Instance.new("Highlight", char)
            highlight.FillColor = Color3.fromRGB(255, 0, 0)
            highlight.OutlineColor = Color3.fromRGB(255, 255, 255)
            highlight.FillTransparency = 0.5
        end
    end
    
    player.CharacterAdded:Connect(applyESP)
    if player.Character then
        applyESP(player.Character)
    end
end

for _, player in pairs(players:GetPlayers()) do
    if player ~= localPlayer then
        createESP(player)
    end
end
players.PlayerAdded:Connect(createESP)
