local active = false
local UIS = game:GetService("UserInputService")
local VU = game:GetService("VirtualUser")

UIS.InputBegan:Connect(function(input)
    if input.KeyCode == Enum.KeyCode.V then
        active = not active
        print("AutoClicker: " .. (active and "ON" or "OFF"))
    end
end)

while true do
    if active then
        VU:CaptureController()
        VU:ClickButton1(Vector2.new(0, 0))
    end
    task.wait(0.1)
end
