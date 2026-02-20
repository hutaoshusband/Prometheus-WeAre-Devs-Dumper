local player = game.Players.LocalPlayer
local mouse = player:GetMouse()
local UIS = game:GetService("UserInputService")

mouse.Button1Down:Connect(function()
    if UIS:IsKeyDown(Enum.KeyCode.LeftControl) then
        local character = player.Character
        if character then
            character:MoveTo(mouse.Hit.p)
        end
    end
end)
