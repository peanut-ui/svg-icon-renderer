--!strict
--!native
--!optimize 2
local Icons = require(script.Parent.Parent.Icons)
local Rasterizer = require(script.Parent.Parent.IconRasterizer)

type Icon = { contours: { { number } }, fillRule: string? }

local iconTable = (Icons :: any).icons :: { [string]: Icon }
local grid = (Icons :: any).grid :: number

local actor = script:GetActor()
if not actor then
    return
end

local resultEvent = script.Parent:WaitForChild("Result") :: BindableEvent

resultEvent:Fire("__ready")

actor:BindToMessageParallel("rasterize", function(name: string, size: number, key: string)
    local icon = iconTable[name]
    if not icon then
        return
    end

    local pixels = Rasterizer.rasterize(
        icon.contours,
        size,
        grid,
        icon.fillRule == "evenodd"
    )

    task.synchronize()
    resultEvent:Fire(key, pixels)
    task.desynchronize()
end)
