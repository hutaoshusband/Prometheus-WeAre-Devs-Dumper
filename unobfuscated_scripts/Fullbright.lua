local lighting = game:GetService("Lighting")
lighting.Brightness = 2
lighting.ClockTime = 14
lighting.FogEnd = 100000
lighting.GlobalShadows = false
lighting.OutdoorAmbient = Color3.fromRGB(128, 128, 128)

lighting.Changed:Connect(function()
    lighting.Brightness = 2
    lighting.ClockTime = 14
    lighting.FogEnd = 100000
    lighting.GlobalShadows = false
end)
