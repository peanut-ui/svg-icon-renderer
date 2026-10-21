--!strict
--!native
--!optimize 2
const AssetService = game:GetService("AssetService")
const RunService = game:GetService("RunService")
const Icons = require(script.Parent.Icons)
const Rasterizer = require(script.Parent.IconRasterizer)

type Icon = { contours: { { number } }, fillRule: string? }
type IconTable = { [string]: Icon }
const iconTable = (Icons :: any).icons :: IconTable
const GRID = (Icons :: any).grid :: number

type Job = { name: string, size: number, key: string, image: EditableImage }

local IconRenderer = {}

export type IconName = string

local cache: { [string]: EditableImage } = {}
local order: { string } = {}
local position: { [string]: number } = {}
local sizes: { [string]: number } = {}
local totalBytes = 0
local cacheBudget = 12 * 1024 * 1024

local queue: { Job } = {}
local pending: { [string]: EditableImage } = {}
local pumping = false
local frameBudget = 0.004

local worker = script.Parent:FindFirstChild("IconWorker") :: Actor?
local actorReady = false
local actorBusy = false
local actorQueue: { Job } = {}
local actorPending: { [string]: EditableImage } = {}

local function keyFor(icon: Icon, size: number): string
    return `{tostring(icon.contours)}@{size}`
end

local function touch(key: string)
    local index = position[key]
    if index == #order then
        return
    end

    table.remove(order, index)
    order[#order + 1] = key

    for i = index, #order do
        position[order[i]] = i
    end
end

local function store(key: string, image: EditableImage, bytes: number)
    cache[key] = image
    sizes[key] = bytes
    totalBytes += bytes

    order[#order + 1] = key
    position[key] = #order

    while totalBytes > cacheBudget and #order > 1 do
        local oldest = table.remove(order, 1) :: string
        position[oldest] = nil

        local evicted = cache[oldest]
        if evicted then
            evicted:Destroy()
            cache[oldest] = nil
        end

        totalBytes -= sizes[oldest] or 0
        sizes[oldest] = nil

        for i = 1, #order do
            position[order[i]] = i
        end
    end
end

local function createImage(size: number): EditableImage?
    return AssetService:CreateEditableImage({
        Size = Vector2.new(size, size),
    })
end

local function rasterizeInto(icon: Icon, size: number, image: EditableImage)
    local pixels = Rasterizer.rasterize(
        icon.contours,
        size,
        GRID,
        icon.fillRule == "evenodd"
    )
    image:WritePixelsBuffer(Vector2.zero, Vector2.new(size, size), pixels)
end

local function rasterize(icon: Icon, size: number): EditableImage?
    local image = createImage(size)
    if not image then
        return nil
    end

    rasterizeInto(icon, size, image)
    return image
end

local function dispatchNext(actor: Actor)
    if actorBusy then
        return
    end

    local job = table.remove(actorQueue, 1)
    if not job then
        return
    end

    actorBusy = true
    actorPending[job.key] = job.image
    actor:SendMessage("rasterize", job.name, job.size, job.key)
end

local function onRasterized(key: string, pixels: buffer)
    actorBusy = false

    local image = actorPending[key]
    if not image then
        return
    end

    actorPending[key] = nil
    image:WritePixelsBuffer(Vector2.zero, Vector2.new(image.Size.X, image.Size.Y), pixels)
    store(key, image, image.Size.X * image.Size.Y * 4)

    local actor = worker
    if actor then
        dispatchNext(actor)
    end
end

if worker then
    local resultEvent = worker:WaitForChild("Result") :: BindableEvent

    resultEvent.Event:Connect(function(key: string, pixels: buffer?)
        if key == "__ready" then
            actorReady = true

            for _, job in queue do
                actorQueue[#actorQueue + 1] = job
            end
            table.clear(queue)
            table.clear(pending)

            dispatchNext(worker :: Actor)
            return
        end

        onRasterized(key, pixels :: buffer)
    end)
end

local function pump()
    local job = table.remove(queue, 1)
    if not job then
        pumping = false
        return
    end

    pending[job.key] = nil

    local icon = iconTable[job.name]
    if icon then
        rasterizeInto(icon, job.size, job.image)
        store(job.key, job.image, job.size * job.size * 4)
    end
end

local function startPump()
    if pumping then
        return
    end

    pumping = true
    task.spawn(function()
        while pumping do
            local started = os.clock()

            while #queue > 0 and os.clock() - started < frameBudget do
                pump()
            end

            if pumping then
                RunService.Heartbeat:Wait()
            end
        end
    end)
end

local function enqueue(name: string, size: number, key: string, image: EditableImage)
    local actor = worker
    if actor and actorReady then
        actorQueue[#actorQueue + 1] = { name = name, size = size, key = key, image = image }
        dispatchNext(actor)
    else
        pending[key] = image
        queue[#queue + 1] = { name = name, size = size, key = key, image = image }
        startPump()
    end
end

function IconRenderer.names(): { string }
    local result = {}
    for name in iconTable do
        table.insert(result, name)
    end
    table.sort(result)
    return result
end

function IconRenderer.has(name: string): boolean
    return iconTable[name] ~= nil
end

function IconRenderer.render(name: string, size: number): EditableImage?
    size = math.max(1, math.floor(size))

    local icon = iconTable[name]
    if not icon then
        return nil
    end

    local key = keyFor(icon, size)
    local cached = cache[key]
    if cached then
        touch(key)
        return cached
    end

    local image = rasterize(icon, size)
    if not image then
        return nil
    end

    store(key, image, size * size * 4)
    return image
end

function IconRenderer.request(name: string, size: number): EditableImage?
    size = math.max(1, math.floor(size))

    local icon = iconTable[name]
    if not icon then
        return nil
    end

    local key = keyFor(icon, size)
    local cached = cache[key]
    if cached then
        touch(key)
        return cached
    end

    local queued = pending[key] or actorPending[key]
    if queued then
        return queued
    end

    local image = createImage(size)
    if not image then
        return nil
    end

    enqueue(name, size, key, image)
    return image
end

function IconRenderer.setCacheBudget(bytes: number)
    cacheBudget = math.max(1, math.floor(bytes))
end

function IconRenderer.setFrameBudget(seconds: number)
    frameBudget = math.max(0, seconds)
end

function IconRenderer.cacheStats(): (number, number, number)
    return #order, totalBytes, cacheBudget
end

function IconRenderer.queueDepth(): number
    return #queue + #actorQueue
end

function IconRenderer.clearCache()
    for _, image in cache do
        image:Destroy()
    end

    table.clear(cache)
    table.clear(order)
    table.clear(position)
    table.clear(sizes)
    table.clear(pending)
    table.clear(actorPending)
    table.clear(queue)
    table.clear(actorQueue)
    totalBytes = 0
end

return table.freeze(IconRenderer)
