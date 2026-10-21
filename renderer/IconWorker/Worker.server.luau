--!strict
--!native
--!optimize 2
local Icons = require(script.Parent.Parent.Icons)
local Rasterizer = require(script.Parent.Parent.IconRasterizer)

local iconTable = (Icons :: any).icons :: { [string]: { { number } } }
local grid = (Icons :: any).grid :: number

local actor = script:GetActor()
if not actor then
    return
end

local resultEvent = script.Parent:WaitForChild("Result") :: BindableEvent

resultEvent:Fire("__ready")

actor:BindToMessageParallel("rasterize", function(name: string, size: number, key: string)
    local contours = iconTable[name]
    if not contours then
        return
    end

    local pixels = Rasterizer.rasterize(contours, size, grid)

    task.synchronize()
    resultEvent:Fire(key, pixels)
    task.desynchronize()
end)
