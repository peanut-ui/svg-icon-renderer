# SVG Icon Renderer

Render SVG icons in Roblox. For real this time.

You give it SVGs, it gives you crisp icons at any size, with no uploads, no
asset IDs, and no waiting on Roblox to load a PNG.

---

## Quick start

If you just want icons and don't care about the compiler, this is the whole
thing:

1. Copy the `renderer/` folder into `ReplicatedStorage`
2. Use it

```lua
local IconRenderer = require(ReplicatedStorage.renderer.IconRenderer)

local image = IconRenderer.request("home", 32)
imageLabel.ImageContent = Content.fromObject(image)
```

The repo ships with a pre-compiled set of ~60 common UI icons, so there's
nothing to build. See [Included icons](#included-icons) for the full list.

If you want your own icons, jump to [Install](#install).

---

## The problem

Roblox has no vector graphics. If you want icons you usually end up doing one of
these:

- Upload a PNG per icon per size, then wait for each one to load
- Use a sprite sheet and do UV math by hand
- Use `ImageLabel` with a decal ID and hope the resolution holds up

All of them are annoying, and none of them scale. A 32px PNG looks like mush at
64px. A 512px PNG wastes memory when you only need 24px. And every single icon
is a round trip to Roblox's asset servers.

## What this does instead

It turns SVG paths into polygon data, ships that as plain Luau, and rasterizes
it at runtime into an `EditableImage`.

So:

- **No uploads.** Icons are code.
- **Any size.** Ask for 24px or 240px, it rasterizes to fit.
- **Instant after first render.** Results are cached.
- **Tiny payload.** Polygon data, not bitmaps.
- **Off the main thread.** Rasterization runs in an Actor.

The whole thing is two pieces: a Python compiler and a Luau renderer.

---

## How it works

### 1. The compiler (Python)

`svg_compile.py` reads an SVG, pulls out the `<path d="...">`, and turns it into
flat integer contours.

The pipeline:

1. **Parse the path** — handles `M L H V C S Q T A Z` and their relative forms
2. **Flatten curves** — cubics and quadratics become line segments, arcs become
   cubics first
3. **Normalize** — reads the SVG's `viewBox` and maps everything into a fixed
   `960x960` grid, so any viewBox works
4. **Clean up** — drops duplicate points and contours with fewer than 3 points
5. **Sort** — orders contours by their top edge, which makes the renderer's
   scanline pass cheaper
6. **Dedupe geometry** — if two icons have identical contours (like `home` and
   `home_filled`), the data is written once and both names point at it

Output is a Luau module with the contours plus a `grid` value.

### 2. The renderer (Luau)

`IconRasterizer.luau` is the actual rasterizer. It's pure math — no Instances, no
`EditableImage`, nothing that would stop it running in parallel.

It uses a scanline fill with the non-zero winding rule:

- Builds an edge list from the contours
- Buckets edges by the row they start on (a flat counting sort, no `table.sort`
  on edge records)
- Walks each row, tracks winding, and fills spans where winding is non-zero
- Supersamples 4x and averages down, so edges come out antialiased

`IconRenderer.luau` is the front end. It owns the cache, hands work to the
Actor, and writes finished pixels into `EditableImage`s.

### 3. The Actor

Rasterizing 180 icons on the main thread is a visible hitch. So the heavy part
runs in an Actor:

```
main thread                     Actor
-----------                     -----
request(name, size)
  create blank EditableImage
  SendMessage("rasterize")  ->  rasterize contours
                                produce RGBA buffer
  WritePixelsBuffer         <-  Fire(key, buffer)
  cache it
  send next job
```

One job is in flight at a time. When a result comes back, the next job goes out.
The main thread only does `WritePixelsBuffer`, which is cheap.

If the Actor isn't there (more on that below), it falls back to a main-thread
pump that spreads work across frames.

---

## Install

### 1. Drop in the renderer

Copy `renderer/` into your project, somewhere under `ReplicatedStorage`.

The folder structure matters, because the Actor setup is done with Rojo meta
files:

```
renderer/
  IconRasterizer.luau
  IconRenderer.luau
  IconWorker/
    init.meta.json          { "className": "Actor" }
    Worker.server.luau
    Worker.meta.json        { "properties": { "RunContext": "Client" } }
    Result/
      init.meta.json        { "className": "BindableEvent" }
```

Three things worth explaining:

- `init.meta.json` with `className: "Actor"` turns the folder into an Actor.
  That's how the Actor exists at build time instead of being created at runtime.
- `Worker.meta.json` sets `RunContext = "Client"`. Without it the script is a
  server `Script` and never runs on the client.
- `Result/` is a `BindableEvent`. The main thread can't `BindToMessage` on an
  Actor (only descendants can), so results come back through this instead.

### 2. Generate your icons

```bash
cd compiler
python build_from_dir.py path/to/your/svgs out/Icons.luau
```

Or if you want Material Symbols specifically:

```bash
python material_symbols.py
```

Material Symbols are picked by name from a hardcoded list at the top of
`material_symbols.py`:

```python
WANTED = [
    "home",
    "menu",
    "search",
    # ...
]
```

Add whatever names you want to that list and run the script again. Names come
from [fonts.google.com/icons](https://fonts.google.com/icons) — use the icon's
snake_case name, like `arrow_back` or `shopping_cart`. Each one is downloaded in
both the regular and filled variant, so you get `home` and `home_filled` from a
single entry.

If a name doesn't exist the download just fails for that one and the rest still
compile, so a typo won't break the whole build.

Then drop the generated `Icons.luau` next to `IconRenderer.luau`:

```
renderer/
  Icons.luau              <- generated, goes here
  IconRasterizer.luau
  IconRenderer.luau
  IconWorker/
```

Everything uses relative requires, so the whole `renderer/` folder can live
anywhere under `ReplicatedStorage`. Just keep the internal layout intact.

---

## Usage

```lua
local IconRenderer = require(ReplicatedStorage.Icons.IconRenderer)

-- Returns an EditableImage immediately. If it isn't cached yet the image is
-- blank and gets filled in on a later frame.
local image = IconRenderer.request("home", 32)

imageLabel.ImageContent = Content.fromObject(image)
```

That's the main one. The rest:

```lua
IconRenderer.render(name, size)        -- synchronous, blocks until done
IconRenderer.names()                   -- every compiled icon name
IconRenderer.has(name)                 -- is this icon compiled?
IconRenderer.setCacheBudget(bytes)     -- default 12 MiB
IconRenderer.setFrameBudget(seconds)   -- fallback pump budget
IconRenderer.cacheStats()              -- entries, bytes used, budget
IconRenderer.queueDepth()              -- pending jobs
IconRenderer.clearCache()              -- destroy everything
```

### Why `request` and not `render`

`request` never blocks. It hands you a blank image straight away and fills it in
the background. Since `EditableImage` updates live, the label just updates on
its own once the pixels land.

`render` is there for tooling and tests where you actually want to wait.

---

## The Actor thing

This is the part that trips people up, so here's the honest version.

Actors don't run everywhere. In a normal playtest they work fine. In Studio
they don't, because it's a plugin sandbox and not a real client.

So the renderer does a handshake. The worker fires `__ready` when it starts. The
main thread only uses the Actor after that. Until then (or if it never happens)
everything goes through the main-thread fallback.

That means:

- **Playtest** — Actor path, rasterization is off the main thread
- **Studio** — fallback path, still works, just uses main-thread time

You don't have to configure anything. It figures it out.

---

## Performance

Numbers from a 256x256 gradient and a set of ~180 icons at 32px:

| | |
|---|---|
| Icon at 32px | ~0.7 ms |
| Warm cache hit | ~0.0009 ms |
| Throughput | ~300 icons/sec |
| Cache budget | 12 MiB default |

The first render of an icon costs about 0.7 ms, but it happens on the Actor, so
the main thread doesn't feel it. After that it's a cache lookup.

---

## Why not just use PNGs

Fair question. Here's the comparison:

| | PNGs | This |
|---|---|---|
| Upload per icon | Yes | No |
| Upload per size | Yes | No |
| Load time | Asset fetch | Local |
| Any size | No | Yes |
| Payload | Bitmaps | Polygon data |

PNGs are simpler if you have a handful of icons at one size. This is better the
moment you want multiple sizes, or you just don't want to deal with the upload
pipeline.

---

## What the compiler supports

Shapes:

- `<path>` — full command set: `M L H V C S Q T A Z` plus relative forms
- `<circle>`, `<ellipse>`
- `<rect>` — including `rx`/`ry` rounded corners
- `<polygon>`, `<polyline>`

Structure:

- `<g>` — nested groups, transforms compose down the tree
- `transform` — `translate`, `scale`, `rotate`, `matrix`, `skewX`, `skewY`
- Any `viewBox` — the compiler reads it and normalizes to a fixed grid, so
  `0 0 24 24`, `0 -960 960 960`, and non-square boxes all work

Holes work the way SVG does it: a single path with an inner contour wound the
opposite direction. Two separate `<circle>` elements are a union, not a donut —
that's correct SVG behavior, not a bug.

---

## Limitations

Being honest about what this doesn't do:

- **No `stroke`.** Stroked paths would need to be converted to filled outlines,
  which is a whole thing (offset curves, joins, caps). Not happening.
- **No `<line>`.** It has no fill area, so there's nothing to rasterize.
- **No `<use>`, `<defs>`, `<clipPath>`, `<mask>`.** No reference resolution.
- **No fill rules other than non-zero.** Even-odd isn't implemented.
- **No gradients or colors in the SVG.** Icons are rendered as a white mask and
  tinted with `ImageColor`.
- **Actors don't work in Studio.** Falls back automatically, but you lose the
  off-thread benefit there.
- **Cache is per-size.** A 24px and a 32px version of the same icon are separate
  entries.

---

## Included icons

The repo ships with these pre-compiled, each in both regular and filled:

<details>
<summary><b>Click to see all 62 icon names</b></summary>

**Navigation**

`home` `menu` `search` `settings` `close` `arrow_back` `arrow_forward`
`chevron_left` `chevron_right` `expand_more` `expand_less` `more_vert`

**Actions**

`add` `remove` `edit` `delete` `save` `check` `content_copy` `share`
`download` `upload` `send` `filter_list` `sort` `refresh`

**Status**

`info` `warning` `error` `help` `check_circle` `cancel` `notifications`
`star` `favorite` `visibility` `visibility_off` `lock`

**People**

`person` `group` `account_circle` `chat` `mail` `call`

**Media**

`play_arrow` `pause` `volume_up` `volume_off` `image` `videocam`

**Files**

`folder` `description` `cloud` `cloud_upload` `cloud_download` `code`

**Misc**

`dashboard` `grid_view` `list` `calendar_today` `schedule` `lightbulb`

</details>

Every name also has a `_filled` variant, so `home` and `home_filled` both work.

Want more? Add names to `WANTED` in `compiler/material_symbols.py` and re-run it.
Any Material Symbol works — grab the snake_case name from
[fonts.google.com/icons](https://fonts.google.com/icons).

---

## Contributing

If you know SVG well and want to take a crack at any of the above — especially
`stroke` support or even-odd fill — I'd genuinely love that. Open an issue or a
PR. Same goes for anything in the renderer.

This started as a tool for one project, so there are probably edge cases I
haven't hit. If you find one, tell me about it.

---

## Repo layout

```
compiler/
  svg_compile.py         SVG -> Luau compiler
  build_from_dir.py      compile a folder of SVGs
  material_symbols.py    download + compile Material Symbols
renderer/
  IconRasterizer.luau    pure rasterizer, no Instances
  IconRenderer.luau      cache, queue, Actor dispatch
  IconWorker/            the Actor + worker script
```

---

## License

MIT. See `LICENSE`.

