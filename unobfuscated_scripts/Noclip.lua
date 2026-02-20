local noclip = true
local player = game.Players.LocalPlayer

game:GetService("RunService").Stepped:Connect(function()
    if noclip then
        if player.Character then
            for _, v in pairs(player.Character:GetDescendants()) do
                if v:IsA("BasePart") then
                    v.CanCollide = false
                end
            end
        end
    end
end)
