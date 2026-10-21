--!strict
--!native
--!optimize 2
local Rasterizer = {}

local SUPERSAMPLE = 3

local alphaScratch: buffer? = nil
local alphaScratchSize = 0

local function getAlphaScratch(bytes: number): buffer
    if not alphaScratch or alphaScratchSize ~= bytes then
        alphaScratch = buffer.create(bytes)
        alphaScratchSize = bytes
    end
    return alphaScratch :: buffer
end

type Edge = {
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    yMin: number,
    yMax: number,
    dir: number,
    slope: number,
    x: number,
}

function Rasterizer.rasterize(contours: { { number } }, size: number, grid: number): buffer
    local hi = size * SUPERSAMPLE
    local scale = hi / grid

    local edges = table.create(64) :: { Edge }

    for _, contour in contours do
        local count = #contour
        local j = count - 1

        for i = 1, count, 2 do
            local x1 = contour[i] * scale
            local y1 = contour[i + 1] * scale
            local x2 = contour[j] * scale
            local y2 = contour[j + 1] * scale

            if y1 ~= y2 then
                edges[#edges + 1] = {
                    x1 = x1,
                    y1 = y1,
                    x2 = x2,
                    y2 = y2,
                    yMin = math.min(y1, y2),
                    yMax = math.max(y1, y2),
                    dir = if y2 > y1 then 1 else -1,
                    slope = (x2 - x1) / (y2 - y1),
                    x = 0,
                }
            end

            j = i
        end
    end

    local rowCount = hi + 1
    local starts = table.create(rowCount) :: { number }
    for i = 1, rowCount do
        starts[i] = 0
    end

    for _, edge in edges do
        local row = math.ceil(edge.yMin - 0.5)
        if row < 0 then
            row = 0
        elseif row > hi - 1 then
            continue
        end
        starts[row + 1] += 1
    end

    local placed = 0
    for i = 1, rowCount do
        local count = starts[i]
        starts[i] = placed
        placed += count
    end

    local bucketEdges = table.create(#edges) :: { Edge }
    local cursor = table.create(rowCount) :: { number }
    for i = 1, rowCount do
        cursor[i] = starts[i]
    end

    for _, edge in edges do
        local row = math.ceil(edge.yMin - 0.5)
        if row < 0 then
            row = 0
        elseif row > hi - 1 then
            continue
        end
        local slot = cursor[row + 1] + 1
        cursor[row + 1] = slot
        bucketEdges[slot] = edge
    end

    local pixels = buffer.create(size * size * 4)
    buffer.fill(pixels, 0, 255, size * size * 4)

    local coverage = getAlphaScratch(size * size)
    buffer.fill(coverage, 0, 0, size * size)

    local samples = SUPERSAMPLE * SUPERSAMPLE
    local alphaScale = 255 / samples

    local active = table.create(16) :: { Edge }
    local crossings = table.create(16) :: { { x: number, dir: number } }

    for y = 0, hi - 1 do
        local sampleY = y + 0.5
        local outY = y // SUPERSAMPLE
        local outRow = outY * size

        local firstEdge = starts[y + 1] + 1
        local lastEdge = starts[y + 2]
        for i = firstEdge, lastEdge do
            local edge = bucketEdges[i]
            edge.x = edge.x1 + (sampleY - edge.y1) * edge.slope
            active[#active + 1] = edge
        end

        local n = 0
        local write = 1
        for read = 1, #active do
            local edge = active[read]
            if edge.yMax > sampleY then
                active[write] = edge
                write += 1

                n += 1
                local slot = crossings[n]
                if slot then
                    slot.x = edge.x
                    slot.dir = edge.dir
                else
                    crossings[n] = { x = edge.x, dir = edge.dir }
                end

                edge.x += edge.slope
            end
        end

        for i = #active, write, -1 do
            active[i] = nil
        end

        if n == 0 then
            continue
        end

        local sorted = table.create(n) :: { { x: number, dir: number } }
        for i = 1, n do
            sorted[i] = crossings[i]
        end
        table.sort(sorted, function(a: { x: number, dir: number }, b: { x: number, dir: number })
            return a.x < b.x
        end)

        local winding = 0
        local spanStart: number? = nil

        for i = 1, n do
            local crossing = sorted[i]
            winding += crossing.dir

            if winding ~= 0 then
                if spanStart == nil then
                    spanStart = crossing.x
                end
            elseif spanStart ~= nil then
                local from = math.max(0, math.floor(spanStart))
                local to = math.min(hi - 1, math.ceil(crossing.x) - 1)

                for px = from, to do
                    local outX = px // SUPERSAMPLE
                    local index = outRow + outX
                    local current = buffer.readu8(coverage, index)
                    if current < 255 then
                        buffer.writeu8(coverage, index, current + 1)
                    end
                end

                spanStart = nil
            end
        end
    end

    local total = size * size
    for i = 0, total - 1 do
        local value = buffer.readu8(coverage, i)
        buffer.writeu8(pixels, i * 4 + 3, math.floor(value * alphaScale + 0.5))
    end

    return pixels
end

return table.freeze(Rasterizer)
