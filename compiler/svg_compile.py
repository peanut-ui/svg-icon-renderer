import math
import re
from os.path import join

GRID = 960

DEFAULT_VIEWBOX = (0.0, 0.0, 960.0, 960.0)

FLATNESS = 0.6

MIN_CONTOUR_POINTS = 3

# Suffix used for the filled variant of an icon. It is a variant, not part of
# the icon's name, so it is stripped when building the base name list.
FILLED_SUFFIX = "_filled"

COMMAND_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)")
NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")

TAG_RE = re.compile(
    r"<(/?)([A-Za-z][\w:-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)(/?)>"
)
ATTR_RE = re.compile(r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")

SHAPE_TAGS = {
    "path",
    "circle",
    "ellipse",
    "rect",
    "polygon",
    "polyline",
}

Matrix = tuple[float, float, float, float, float, float]

IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def parse_numbers(text: str) -> list[float]:
    return [float(match) for match in NUMBER_RE.findall(text)]


def parse_attrs(text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in ATTR_RE.finditer(text):
        value = match.group(2)
        if value is None:
            value = match.group(3)
        attrs[match.group(1)] = value
    return attrs


def multiply(a: Matrix, b: Matrix) -> Matrix:
    a0, a1, a2, a3, a4, a5 = a
    b0, b1, b2, b3, b4, b5 = b
    return (
        a0 * b0 + a2 * b1,
        a1 * b0 + a3 * b1,
        a0 * b2 + a2 * b3,
        a1 * b2 + a3 * b3,
        a0 * b4 + a2 * b5 + a4,
        a1 * b4 + a3 * b5 + a5,
    )


def apply_matrix(
    matrix: Matrix,
    point: tuple[float, float],
) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


def parse_transform(text: str) -> Matrix:
    result = IDENTITY

    for match in re.finditer(r"([a-zA-Z]+)\s*\(([^)]*)\)", text):
        name = match.group(1)
        args = parse_numbers(match.group(2))

        if name == "translate" and args:
            tx = args[0]
            ty = args[1] if len(args) > 1 else 0.0
            step: Matrix = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif name == "scale" and args:
            sx = args[0]
            sy = args[1] if len(args) > 1 else sx
            step = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate" and args:
            angle = math.radians(args[0])
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            step = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                step = multiply(
                    (1.0, 0.0, 0.0, 1.0, cx, cy),
                    multiply(step, (1.0, 0.0, 0.0, 1.0, -cx, -cy)),
                )
        elif name == "matrix" and len(args) >= 6:
            step = (args[0], args[1], args[2], args[3], args[4], args[5])
        elif name == "skewX" and args:
            step = (1.0, 0.0, math.tan(math.radians(args[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and args:
            step = (1.0, math.tan(math.radians(args[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            continue

        result = multiply(result, step)

    return result


def transform_contours(
    contours: list[list[tuple[float, float]]],
    matrix: Matrix,
) -> list[list[tuple[float, float]]]:
    if matrix == IDENTITY:
        return contours

    return [
        [apply_matrix(matrix, point) for point in contour]
        for contour in contours
    ]


def circle_path(cx: float, cy: float, rx: float, ry: float) -> str:
    return (
        f"M{cx - rx} {cy} "
        f"a{rx} {ry} 0 1 0 {2 * rx} 0 "
        f"a{rx} {ry} 0 1 0 {-2 * rx} 0 Z"
    )


def rect_path(
    x: float,
    y: float,
    width: float,
    height: float,
    rx: float,
    ry: float,
) -> str:
    if rx <= 0 and ry <= 0:
        return (
            f"M{x} {y} L{x + width} {y} L{x + width} {y + height} "
            f"L{x} {y + height} Z"
        )

    if rx <= 0:
        rx = ry
    if ry <= 0:
        ry = rx

    rx = min(rx, width / 2)
    ry = min(ry, height / 2)

    return (
        f"M{x + rx} {y} "
        f"L{x + width - rx} {y} "
        f"a{rx} {ry} 0 0 1 {rx} {ry} "
        f"L{x + width} {y + height - ry} "
        f"a{rx} {ry} 0 0 1 {-rx} {ry} "
        f"L{x + rx} {y + height} "
        f"a{rx} {ry} 0 0 1 {-rx} {-ry} "
        f"L{x} {y + ry} "
        f"a{rx} {ry} 0 0 1 {rx} {-ry} Z"
    )


def points_path(points: list[float], close: bool) -> str:
    if len(points) < 4:
        return ""

    parts = [f"M{points[0]} {points[1]}"]
    for i in range(2, len(points) - 1, 2):
        parts.append(f"L{points[i]} {points[i + 1]}")

    if close:
        parts.append("Z")

    return " ".join(parts)


def shape_to_path(tag: str, attrs: dict[str, str]) -> str:
    def number(name: str, default: float = 0.0) -> float:
        raw = attrs.get(name)
        if raw is None:
            return default
        values = parse_numbers(raw)
        return values[0] if values else default

    if tag == "path":
        return attrs.get("d", "")

    if tag == "circle":
        r = number("r")
        return circle_path(number("cx"), number("cy"), r, r)

    if tag == "ellipse":
        return circle_path(
            number("cx"), number("cy"), number("rx"), number("ry")
        )

    if tag == "rect":
        return rect_path(
            number("x"),
            number("y"),
            number("width"),
            number("height"),
            number("rx"),
            number("ry"),
        )

    if tag == "polygon":
        return points_path(parse_numbers(attrs.get("points", "")), True)

    if tag == "polyline":
        return points_path(parse_numbers(attrs.get("points", "")), False)

    return ""


def extract_contours(svg: str) -> list[list[tuple[float, float]]]:
    contours: list[list[tuple[float, float]]] = []
    stack: list[Matrix] = [IDENTITY]

    for match in TAG_RE.finditer(svg):
        closing = match.group(1) == "/"
        tag = match.group(2).lower()
        attrs = parse_attrs(match.group(3))
        self_closing = match.group(4) == "/"

        if closing:
            if tag == "g" and len(stack) > 1:
                stack.pop()
            continue

        parent = stack[-1]
        local = parse_transform(attrs.get("transform", ""))
        current = multiply(parent, local)

        if tag == "g":
            if not self_closing:
                stack.append(current)
            continue

        if tag in SHAPE_TAGS:
            d = shape_to_path(tag, attrs)
            if not d:
                continue

            for contour in parse_path(d):
                contours.append(
                    [apply_matrix(current, point) for point in contour]
                )

    return contours


def flatten_quadratic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    out: list[tuple[float, float]],
    depth: int = 0,
) -> None:
    dx = p2[0] - p0[0]
    dy = p2[1] - p0[1]
    d = abs((p1[0] - p2[0]) * dy - (p1[1] - p2[1]) * dx)

    if depth >= 16 or d * d <= FLATNESS * (dx * dx + dy * dy):
        out.append(p2)
        return

    m01 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    m12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    mid = ((m01[0] + m12[0]) / 2, (m01[1] + m12[1]) / 2)

    flatten_quadratic(p0, m01, mid, out, depth + 1)
    flatten_quadratic(mid, m12, p2, out, depth + 1)


def flatten_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    out: list[tuple[float, float]],
    depth: int = 0,
) -> None:
    dx = p3[0] - p0[0]
    dy = p3[1] - p0[1]
    d1 = abs((p1[0] - p3[0]) * dy - (p1[1] - p3[1]) * dx)
    d2 = abs((p2[0] - p3[0]) * dy - (p2[1] - p3[1]) * dx)
    d = d1 + d2

    if depth >= 16 or d * d <= FLATNESS * (dx * dx + dy * dy):
        out.append(p3)
        return

    m01 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    m12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    m23 = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
    m012 = ((m01[0] + m12[0]) / 2, (m01[1] + m12[1]) / 2)
    m123 = ((m12[0] + m23[0]) / 2, (m12[1] + m23[1]) / 2)
    mid = ((m012[0] + m123[0]) / 2, (m012[1] + m123[1]) / 2)

    flatten_cubic(p0, m01, m012, mid, out, depth + 1)
    flatten_cubic(mid, m123, m23, p3, out, depth + 1)


def arc_to_cubics(
    p0: tuple[float, float],
    rx: float,
    ry: float,
    rotation: float,
    large_arc: bool,
    sweep: bool,
    p1: tuple[float, float],
) -> list[tuple[tuple[float, float], ...]]:
    if rx == 0 or ry == 0 or p0 == p1:
        return []

    phi = math.radians(rotation)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx2 = (p0[0] - p1[0]) / 2
    dy2 = (p0[1] - p1[1]) / 2
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    rx = abs(rx)
    ry = abs(ry)

    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    sign = -1 if large_arc == sweep else 1
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = sign * math.sqrt(max(0.0, num / den))

    cxp = coef * (rx * y1p / ry)
    cyp = coef * -(ry * x1p / rx)

    cx = cos_phi * cxp - sin_phi * cyp + (p0[0] + p1[0]) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (p0[1] + p1[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        length = math.hypot(ux, uy) * math.hypot(vx, vy)
        if length == 0:
            return 0.0
        value = max(-1.0, min(1.0, dot / length))
        result = math.acos(value)
        if ux * vy - uy * vx < 0:
            result = -result
        return result

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle(
        (x1p - cxp) / rx,
        (y1p - cyp) / ry,
        (-x1p - cxp) / rx,
        (-y1p - cyp) / ry,
    )

    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    segments = max(1, int(math.ceil(abs(delta) / (math.pi / 2))))
    step = delta / segments
    alpha = 4 / 3 * math.tan(step / 4)

    cubics = []
    for i in range(segments):
        t1 = theta1 + i * step
        t2 = t1 + step

        cos1, sin1 = math.cos(t1), math.sin(t1)
        cos2, sin2 = math.cos(t2), math.sin(t2)

        def point(c: float, s: float) -> tuple[float, float]:
            x = cx + rx * cos_phi * c - ry * sin_phi * s
            y = cy + rx * sin_phi * c + ry * cos_phi * s
            return (x, y)

        def tangent(c: float, s: float) -> tuple[float, float]:
            x = -rx * cos_phi * s - ry * sin_phi * c
            y = -rx * sin_phi * s + ry * cos_phi * c
            return (x, y)

        start = point(cos1, sin1)
        end = point(cos2, sin2)
        t_start = tangent(cos1, sin1)
        t_end = tangent(cos2, sin2)

        c1 = (start[0] + alpha * t_start[0], start[1] + alpha * t_start[1])
        c2 = (end[0] - alpha * t_end[0], end[1] - alpha * t_end[1])

        cubics.append((start, c1, c2, end))

    return cubics


def parse_path(d: str) -> list[list[tuple[float, float]]]:
    contours: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    x = y = 0.0
    start_x = start_y = 0.0
    prev_cmd = ""
    prev_ctrl: tuple[float, float] | None = None

    def flush() -> None:
        nonlocal current
        if len(current) >= MIN_CONTOUR_POINTS:
            contours.append(current)
        current = []

    for match in COMMAND_RE.finditer(d):
        cmd = match.group(1)
        args = parse_numbers(match.group(2))
        upper = cmd.upper()
        relative = cmd.islower()

        i = 0
        while i < len(args) or upper in ("Z",):
            if upper == "M":
                if i + 2 > len(args):
                    break
                nx, ny = args[i], args[i + 1]
                i += 2
                if relative:
                    nx += x
                    ny += y
                flush()
                x, y = nx, ny
                start_x, start_y = x, y
                current = [(x, y)]
                upper = "L"
                prev_ctrl = None

            elif upper == "L":
                if i + 2 > len(args):
                    break
                nx, ny = args[i], args[i + 1]
                i += 2
                if relative:
                    nx += x
                    ny += y
                x, y = nx, ny
                current.append((x, y))
                prev_ctrl = None

            elif upper == "H":
                if i + 1 > len(args):
                    break
                nx = args[i]
                i += 1
                if relative:
                    nx += x
                x = nx
                current.append((x, y))
                prev_ctrl = None

            elif upper == "V":
                if i + 1 > len(args):
                    break
                ny = args[i]
                i += 1
                if relative:
                    ny += y
                y = ny
                current.append((x, y))
                prev_ctrl = None

            elif upper == "C":
                if i + 6 > len(args):
                    break
                x1, y1, x2, y2, nx, ny = args[i:i + 6]
                i += 6
                if relative:
                    x1 += x
                    y1 += y
                    x2 += x
                    y2 += y
                    nx += x
                    ny += y
                flatten_cubic((x, y), (x1, y1), (x2, y2), (nx, ny), current)
                prev_ctrl = (x2, y2)
                x, y = nx, ny

            elif upper == "S":
                if i + 4 > len(args):
                    break
                x2, y2, nx, ny = args[i:i + 4]
                i += 4
                if relative:
                    x2 += x
                    y2 += y
                    nx += x
                    ny += y
                if prev_cmd in ("C", "S") and prev_ctrl:
                    x1 = 2 * x - prev_ctrl[0]
                    y1 = 2 * y - prev_ctrl[1]
                else:
                    x1, y1 = x, y
                flatten_cubic((x, y), (x1, y1), (x2, y2), (nx, ny), current)
                prev_ctrl = (x2, y2)
                x, y = nx, ny

            elif upper == "Q":
                if i + 4 > len(args):
                    break
                x1, y1, nx, ny = args[i:i + 4]
                i += 4
                if relative:
                    x1 += x
                    y1 += y
                    nx += x
                    ny += y
                flatten_quadratic((x, y), (x1, y1), (nx, ny), current)
                prev_ctrl = (x1, y1)
                x, y = nx, ny

            elif upper == "T":
                if i + 2 > len(args):
                    break
                nx, ny = args[i], args[i + 1]
                i += 2
                if relative:
                    nx += x
                    ny += y
                if prev_cmd in ("Q", "T") and prev_ctrl:
                    x1 = 2 * x - prev_ctrl[0]
                    y1 = 2 * y - prev_ctrl[1]
                else:
                    x1, y1 = x, y
                flatten_quadratic((x, y), (x1, y1), (nx, ny), current)
                prev_ctrl = (x1, y1)
                x, y = nx, ny

            elif upper == "A":
                if i + 7 > len(args):
                    break
                rx, ry, rot, large, sweep, nx, ny = args[i:i + 7]
                i += 7
                if relative:
                    nx += x
                    ny += y
                for cubic in arc_to_cubics(
                    (x, y), rx, ry, rot, bool(large), bool(sweep), (nx, ny)
                ):
                    flatten_cubic(*cubic, current)  # type: ignore
                x, y = nx, ny
                prev_ctrl = None

            elif upper == "Z":
                if current:
                    current.append((start_x, start_y))
                flush()
                x, y = start_x, start_y
                prev_ctrl = None
                break

            else:
                break

        prev_cmd = upper

    flush()
    return contours


def normalize(
    contours: list[list[tuple[float, float]]],
    viewbox: tuple[float, float, float, float],
) -> list[list[int]]:
    min_x, min_y, width, height = viewbox
    scale = GRID / max(width, height)
    result: list[list[int]] = []

    for contour in contours:
        flat: list[int] = []
        for px, py in contour:
            gx = round((px - min_x) * scale)
            gy = round((py - min_y) * scale)
            flat.append(gx)
            flat.append(gy)
        result.append(flat)

    return result


def dedupe_contour(contour: list[int]) -> list[int]:
    result: list[int] = []

    for i in range(0, len(contour), 2):
        x = contour[i]
        y = contour[i + 1]

        if result:
            last_x = result[-2]
            last_y = result[-1]
            if x == last_x and y == last_y:
                continue

        result.append(x)
        result.append(y)

    while len(result) >= 4:
        if result[0] == result[-2] and result[1] == result[-1]:
            del result[-2:]
        else:
            break

    return result


def clean_contours(contours: list[list[int]]) -> list[list[int]]:
    cleaned: list[list[int]] = []

    for contour in contours:
        deduped = dedupe_contour(contour)
        if len(deduped) >= MIN_CONTOUR_POINTS * 2:
            cleaned.append(deduped)

    return cleaned


def contour_y_range(contour: list[int]) -> tuple[int, int]:
    y_min = GRID
    y_max = 0

    for i in range(1, len(contour), 2):
        y = contour[i]
        if y < y_min:
            y_min = y
        if y > y_max:
            y_max = y

    if y_min > y_max:
        return (0, 0)

    return (y_min, y_max)


def sort_contours(contours: list[list[int]]) -> list[list[int]]:
    return sorted(contours, key=lambda contour: contour_y_range(contour)[0])


def parse_viewbox(svg: str) -> tuple[float, float, float, float]:
    match = re.search(r'viewBox="([^"]+)"', svg)
    if match:
        parts = parse_numbers(match.group(1))
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return (parts[0], parts[1], parts[2], parts[3])

    width = re.search(r'\bwidth="([\d.]+)"', svg)
    height = re.search(r'\bheight="([\d.]+)"', svg)
    if width and height:
        w = float(width.group(1))
        h = float(height.group(1))
        if w > 0 and h > 0:
            return (0.0, 0.0, w, h)

    return DEFAULT_VIEWBOX


def compile_svg(svg: str) -> list[list[int]]:
    viewbox = parse_viewbox(svg)
    contours = extract_contours(svg)
    return sort_contours(clean_contours(normalize(contours, viewbox)))


def local_name_for(name: str) -> str:
    return "_" + name


def contour_lines(contours: list[list[int]], indent: str) -> list[str]:
    lines: list[str] = []
    for contour in contours:
        points = ", ".join(str(value) for value in contour)
        lines.append(f"{indent}{{ {points} }},")
    return lines


def type_union_lines(
    type_name: str,
    names: list[str],
    comment: str,
    chunk_size: int,
) -> list[str]:
    lines = [f"--- {comment}"]

    if not names:
        lines.append(f"export type {type_name} = never")
        lines.append("")
        return lines

    if len(names) <= chunk_size:
        lines.append(f"export type {type_name} =")
        for name in names:
            lines.append(f'    | "{name}"')
        lines.append("")
        return lines

    parts: list[str] = []
    for i in range(0, len(names), chunk_size):
        chunk = names[i:i + chunk_size]
        part_name = f"{type_name}Part{i // chunk_size}"
        parts.append(part_name)

        lines.append(f"type {part_name} =")
        for name in chunk:
            lines.append(f'    | "{name}"')
        lines.append("")

    lines.append(f"export type {type_name} =")
    for part in parts:
        lines.append(f"    | {part}")
    lines.append("")

    return lines


def format_luau(icons: dict[str, list[list[int]]]) -> str:
    groups: dict[str, list[str]] = {}
    for name in sorted(icons):
        key = repr(icons[name])
        groups.setdefault(key, []).append(name)

    lines = [
        "--!strict",
        "--!optimize 2",
        "-- Generated by svg_compile.py. Do not edit by hand.",
        "",
        "export type Contour = { number }",
        "",
        "export type IconData = {",
        "    grid: number,",
        "    icons: { [string]: { Contour } },",
        "}",
        "",
    ]

    all_names = sorted(name for names in groups.values() for name in names)
    base_names = sorted(
        name for name in all_names if not name.endswith(FILLED_SUFFIX)
    )

    lines.extend(type_union_lines(
        "IconName",
        base_names,
        "Base icon names, without any variant suffix.",
        200,
    ))
    lines.extend(type_union_lines(
        "IconNameFull",
        all_names,
        "Every key in the icon table, including variants.",
        200,
    ))

    shared = [(key, names) for key, names in groups.items() if len(names) > 1]
    unique = [(key, names) for key, names in groups.items() if len(names) == 1]

    CHUNK = 150
    chunks: list[list[tuple[str, list[str]]]] = []
    for i in range(0, len(shared), CHUNK):
        chunks.append(shared[i:i + CHUNK])

    for index, chunk in enumerate(chunks):
        lines.append(f"local function shared{index}(icons: any): ()")

        for key, names in chunk:
            local_name = local_name_for(names[0])
            lines.append(f"    local {local_name} = {{")
            lines.extend(contour_lines(icons[names[0]], "        "))
            lines.append("    }")

        lines.append("")

        for key, names in chunk:
            local_name = local_name_for(names[0])
            for name in names:
                lines.append(f"    icons[\"{name}\"] = {local_name}")

        lines.append("end")
        lines.append("")

    lines.append("local icons: any = {")

    for key, names in unique:
        name = names[0]
        lines.append(f"    [\"{name}\"] = {{")
        lines.extend(contour_lines(icons[name], "        "))
        lines.append("    },")

    lines.append("}")
    lines.append("")

    for index, chunk in enumerate(chunks):
        lines.append(f"shared{index}(icons)")
    lines.append("")

    lines.append("return {")
    lines.append(f"    grid = {GRID},")
    lines.append("    icons = icons :: any,")
    lines.append("} :: IconData")
    lines.append("")

    return "\n".join(lines)


def compile_icon_file(path: str) -> list[list[int]]:
    with open(path, encoding="utf-8") as file:
        return compile_svg(file.read())


def write_luau(icons: dict[str, list[list[int]]], dest: str) -> None:
    with open(dest, "w", encoding="utf-8") as file:
        file.write(format_luau(icons))


def default_out_path(script_dir: str) -> str:
    return join(script_dir, "out", "Icons.luau")
