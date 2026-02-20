local player = game.Players.LocalPlayer
local mouse = player:GetMouse()
local flySpeed = 50
local flying = false

mouse.KeyDown:Connect(function(key)
    if key:lower() == "f" then
        flying = not flying
        local character = player.Character
        if not character then return end
        local root = character:FindFirstChild("HumanoidRootPart")
        if not root then return end
        
        if flying then
            local bv = Instance.new("BodyVelocity")
            bv.Velocity = Vector3.new(0,0,0)
            bv.MaxForce = Vector3.new(math.huge, math.huge, math.huge)
            bv.Name = "FlyVelocity"
            bv.Parent = root
            
            spawn(function()
                while flying do
                    bv.Velocity = workspace.CurrentCamera.CFrame.LookVector * flySpeed
                    task.wait()
                end
                bv:Destroy()
            end)
        end
    end
end)
