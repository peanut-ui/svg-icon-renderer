# Contributing

Hey, glad you're here. This started as a tool for one project and turned into
something people actually use, so contributions are very welcome.

Before you dive in, a few things about how this repo works.

---

## The one rule

**Profile it before you PR it.**

This is a renderer. It runs inside a game loop. Every millisecond matters, and
"it works" is not the same as "it's fast enough".

If you're touching the rasterizer, the compiler, or anything in the hot path,
measure it. Not vibes — actual numbers.

```lua
local start = os.clock()
-- your code
print(`{(os.clock() - start) * 1000} ms`)
```

Or use Studio's built-in profiler. Either way, come with numbers.

If your change makes something slower, say so and explain why it's worth it. If
it makes something faster, show the before and after. I'd rather merge a slower
change with a good reason than a faster one with no evidence.

---

## What "optimized" means here

Some things I've learned the hard way while building this:

**Native calls are expensive.** `math.floor`, `bit32.*`, `buffer.writeu8` — each
one is a call into the VM. In a loop that runs 65,000 times, they add up fast.
Sometimes it's cheaper to do the math inline than to call a helper.

**Call count beats call cost.** Four `writeu8` calls are slower than one
`writeu32`, even though `writeu32` does more work. Fewer calls wins.

**Lookup tables beat computation.** If a value only has 17 possible results,
precompute them. `ALPHA_LUT[value + 1]` is faster than
`math.floor(value * scale + 0.5)`.

**But tables have edges.** A LUT with 17 entries breaks if you index 18. Make
sure your domain is actually bounded, or clamp it.

**`math.*` is already optimized.** Luau has fastcall for the whole math library
and hoists global chains at load time. `local floor = math.floor` does nothing.
Don't bother.

**`buffer.*` is not.** No fastcall yet. But `GETIMPORT` still hoists the lookup,
so localizing it doesn't help either. It is what it is.

**Allocations in loops are the enemy.** `table.create` outside the loop, reuse
buffers, avoid creating tables per row.

---

## How to profile

Wrap the thing you're changing in `os.clock()` and print the delta. That's it.

**Run it more than once.** A single measurement is noise. Run it 10-20 times and
average the results, or take the median. The first run is usually slower because
of caching, so throw it away.

**Close everything else.** Background processes, other Studio windows, a browser
with 40 tabs — all of it skews the numbers. If you can't get a clean machine,
at least run the same test back to back so the noise affects both equally.

If you're adding a feature, profile the *before* state first. Otherwise you have
nothing to compare against.

And please — test with more than one icon. A single simple icon will hide
problems that show up on a 40-contour monster.

---

## Code style

Nothing fancy. Match what's there:

- `--!strict`, `--!native`, `--!optimize 2` at the top of every module
- Types on function signatures
- `local` everything, no globals
- Comments only where the code isn't obvious. Don't narrate what the line does,
  explain *why* it's there.

The compiler is Python and follows the same idea — keep it readable, keep it
typed.

---

## Adding SVG features

This is the most likely thing you'll want to do, so here's the shape of it.

The data format is designed to be extended. An icon looks like this:

```lua
["home"] = {
    contours = { { 1, 2, 3 }, { 4, 5, 6 } },
    fillRule = "evenodd",  -- optional, defaults to nonzero
}
```

Adding a field is **not** a breaking change. Old icons just don't have it, and
the renderer falls back to a default. So if you want to add `fill`, `opacity`,
`stroke`, whatever — add the field, handle the default, done.

The pipeline is:

1. **`svg_compile.py`** parses the SVG and produces contours
2. **`format_luau`** writes them out
3. **`IconRasterizer.luau`** turns contours into pixels
4. **`IconRenderer.luau`** handles caching and the Actor

If you're adding a feature, you'll probably touch all four. That's fine, just
keep them in sync.

**Test it visually.** The easiest way is to render the icon in Studio and look at
it. For a quicker loop, you can rasterize the contours in Python and write a PNG
— the algorithm is simple enough to port in a few lines if you need it.

---

## Things I'd love help with

In rough order of how much I want them:

**`stroke` support.** This is the big one. Stroked paths need to be converted to
filled outlines, which means offset curves, joins, caps, and dashes. It's a real
project. If you know how to do this well, please.

**Solid fills.** Multi-color icons. Rasterize per color group so you get one
pass per color, not one per shape.

**`<use>` and `<defs>`.** Reference resolution. Icon sets reuse shapes a lot.

**`<clipPath>` and `<mask>`.** Some icons clip their content.

**Gradients.** Linear and radial. This is basically merging the gradient
renderer into the rasterizer, so it's a decent chunk of work.

**Even more performance.** There's always more. If you find a win, I want to
hear about it.

---

## What I'd rather you didn't do

**Don't add a dependency.** This is meant to be droppable into any project. No
Wally packages, no external modules, no "just install this first".

**Don't break the data format.** Add fields, don't rename them. People have
generated `Icons.luau` files in their projects and I don't want to make them
regenerate.

**Don't optimize without measuring.** See the first rule.

**Don't add features nobody asked for.** If you want something, open an issue
first and let's talk about it. I'd rather discuss the design than review a
surprise PR.

---

## Opening a PR

Small and focused beats big and sprawling. One feature, one PR.

In the description, tell me:

- What it does
- How you tested it
- What the performance impact is (with numbers if it's in the hot path)
- Anything you're unsure about

If it's a visual change, include a screenshot or a short clip. I can't merge
what I can't see.

---

## Found a bug?

Open an issue. Include:

- What you expected
- What happened
- A minimal repro if you can
- The SVG that broke it, if it's a compiler issue

If it's a rendering bug, a screenshot helps a lot.

---

## One last thing

This is a hobby project that got out of hand. I'll review PRs when I can, and I
might ask questions or suggest changes. That's not me being difficult — I just
want to keep the thing fast and clean.

If you're unsure about something, ask. I'd rather answer a question than reject
a PR.

Thanks for reading. Go build something cool.
