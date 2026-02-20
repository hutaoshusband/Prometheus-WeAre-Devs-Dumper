local ScreenGui = Instance.new("ScreenGui")
local Frame = Instance.new("Frame")
local SpeedButton = Instance.new("TextButton")
local JumpButton = Instance.new("TextButton")

ScreenGui.Parent = game.CoreGui
ScreenGui.Name = "SimpleModMenu"

Frame.Parent = ScreenGui
Frame.Size = UDim2.new(0, 200, 0, 150)
Frame.Position = UDim2.new(0.5, -100, 0.5, -75)
Frame.BackgroundColor3 = Color3.fromRGB(30, 30, 30)
Frame.Active = true
Frame.Draggable = true

SpeedButton.Parent = Frame
SpeedButton.Size = UDim2.new(0, 180, 0, 40)
SpeedButton.Position = UDim2.new(0, 10, 0, 20)
SpeedButton.Text = "Set Speed (100)"
SpeedButton.BackgroundColor3 = Color3.fromRGB(60, 60, 60)
SpeedButton.TextColor3 = Color3.fromRGB(255, 255, 255)

SpeedButton.MouseButton1Click:Connect(function()
    local char = game.Players.LocalPlayer.Character
    if char and char:FindFirstChild("Humanoid") then
        char.Humanoid.WalkSpeed = 100
    end
end)

JumpButton.Parent = Frame
JumpButton.Size = UDim2.new(0, 180, 0, 40)
JumpButton.Position = UDim2.new(0, 10, 0, 70)
JumpButton.Text = "Set JumpPower (100)"
JumpButton.BackgroundColor3 = Color3.fromRGB(60, 60, 60)
JumpButton.TextColor3 = Color3.fromRGB(255, 255, 255)

JumpButton.MouseButton1Click:Connect(function()
    local char = game.Players.LocalPlayer.Character
    if char and char:FindFirstChild("Humanoid") then
        char.Humanoid.JumpPower = 100
    end
end)
