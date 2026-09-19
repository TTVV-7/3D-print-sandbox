"""Read an SVG and hand back filled polygons.

Standard library only, like the rest of this repository, so this is a real
parser rather than a call into a library: path data (every command, arcs
included), the basic shapes, nested transforms, and inherited fill.

Two decisions worth knowing about before you export:

**Strokes are converted to fills.** A lot of line art has no fills at all,
and silently printing nothing would be a poor answer. Each stroked segment
becomes a quad and each joint a disc, all wound the same way so the nonzero
rule unions them. A 0.2 mm stroke scaled down to less than a nozzle width
will still not print -- see :func:`report` for the warning.

**Text is not rendered.** Rendering text means shipping a font and a shaper.
Convert text to paths in your editor before exporting; the warning says so.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


SVG_NS = "{http://www.w3.org/2000/svg}"

#: The CSS named colours people actually type. Anything else falls back to
#: black and is listed in the warnings.
NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "lime": (0, 255, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "cyan": (0, 255, 255), "aqua": (0, 255, 255),
    "magenta": (255, 0, 255), "fuchsia": (255, 0, 255), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "silver": (192, 192, 192), "maroon": (128, 0, 0),
    "olive": (128, 128, 0), "navy": (0, 0, 128), "teal": (0, 128, 128),
    "purple": (128, 0, 128), "orange": (255, 165, 0), "pink": (255, 192, 203),
    "brown": (165, 42, 42), "gold": (255, 215, 0), "beige": (245, 245, 220),
    "ivory": (255, 255, 240), "coral": (255, 127, 80), "salmon": (250, 128, 114),
    "khaki": (240, 230, 140), "violet": (238, 130, 238),
    "indigo": (75, 0, 130), "turquoise": (64, 224, 208),
    "crimson": (220, 20, 60), "darkblue": (0, 0, 139),
    "darkgreen": (0, 100, 0), "darkred": (139, 0, 0),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211),
    "transparent": None, "none": None,
}

Point = tuple[float, float]


@dataclass
class Shape:
    """One filled region: closed subpaths plus the colour to fill them with."""

    subpaths: list[list[Point]]
    rgb: tuple[int, int, int]
    even_odd: bool = False
    #: Where it came from, for the warnings and the colour listing.
    origin: str = "path"

    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for sp in self.subpaths for p in sp]
        ys = [p[1] for sp in self.subpaths for p in sp]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass
class Art:
    """A parsed SVG: shapes in document order, bottom of the stack first."""

    shapes: list[Shape] = field(default_factory=list)
    #: The viewBox, or the bounding box of the geometry if there is none.
    view: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    warnings: list[str] = field(default_factory=list)

    def bbox(self) -> tuple[float, float, float, float]:
        if not self.shapes:
            return self.view
        boxes = [s.bbox() for s in self.shapes]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def colours(self) -> list[tuple[tuple[int, int, int], float]]:
        """Distinct fill colours, with a rough area each, biggest first."""
        areas: dict[tuple[int, int, int], float] = {}
        for s in self.shapes:
            a = sum(abs(_signed_area(sp)) for sp in s.subpaths)
            areas[s.rgb] = areas.get(s.rgb, 0.0) + a
        return sorted(areas.items(), key=lambda kv: -kv[1])


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"([MmZzLlHhVvCcSsQqTtAa])")


#: Refused outright rather than parsed. ElementTree does not fetch external
#: entities, but it does expand internal ones, and a dozen nested entity
#: definitions expand to gigabytes before any of this code sees a shape. No
#: drawing program emits a DOCTYPE in an SVG, so nothing real is lost.
_DOCTYPE = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.I)

#: An SVG larger than this is not a drawing, it is a payload.
MAX_BYTES = 4 << 20
#: A shape count past this is a stress test, not artwork.
MAX_SHAPES = 20_000


def load(text: str, *, flatness: float = 0.05, limit: bool = True) -> Art:
    """Parse SVG source into filled polygons.

    ``limit`` bounds the work an untrusted file can ask for. Leave it on for
    anything that arrived over a network; the numbers are far above what a
    drawing needs and far below what hurts.
    """
    if limit:
        if len(text) > MAX_BYTES:
            raise ValueError(
                f"SVG is {len(text) / 1e6:.1f} MB; the limit is "
                f"{MAX_BYTES / 1e6:.0f} MB")
        found = _DOCTYPE.search(text)
        if found:
            raise ValueError(
                f"SVG declares a {found.group(1).upper()}, which is refused: "
                "entity definitions expand without bound. Re-export it from "
                "your drawing program, which will not emit one")

    art = Art()
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"not valid XML: {exc}") from None

    gradients = _gradient_stops(root)
    vb = root.get("viewBox")
    if vb:
        nums = [float(n) for n in _NUM.findall(vb)]
        if len(nums) == 4:
            art.view = (nums[0], nums[1], nums[0] + nums[2], nums[1] + nums[3])
    elif root.get("width") and root.get("height"):
        art.view = (0.0, 0.0, _len(root.get("width")), _len(root.get("height")))

    unsupported: set[str] = set()
    _walk(root, (1, 0, 0, 1, 0, 0), {}, art, gradients, unsupported, flatness)
    if limit and len(art.shapes) > MAX_SHAPES:
        raise ValueError(
            f"SVG holds {len(art.shapes)} filled shapes; the limit is "
            f"{MAX_SHAPES}. Flatten or simplify it first")

    if not vb and art.shapes:
        art.view = art.bbox()
    for tag in sorted(unsupported):
        if tag == "text":
            art.warnings.append(
                "<text> is not rendered; convert text to paths before export")
        else:
            art.warnings.append(f"<{tag}> is not supported and was skipped")
    if not art.shapes:
        art.warnings.append("nothing fillable in this SVG")
    return art


def _walk(el, mat, inherited, art, gradients, unsupported, flatness) -> None:
    tag = el.tag.replace(SVG_NS, "")
    style = dict(inherited)
    style.update(_style_of(el))
    if style.get("display") == "none" or style.get("visibility") == "hidden":
        return
    if _num_or(style.get("opacity"), 1.0) <= 0.01:
        return

    mat = _mul(mat, _transform(el.get("transform")))

    if tag in ("svg", "g", "a", "switch"):
        for child in el:
            _walk(child, mat, style, art, gradients, unsupported, flatness)
        return
    if tag in ("defs", "clipPath", "mask", "symbol", "marker", "title",
               "desc", "style", "metadata", "linearGradient",
               "radialGradient", "filter"):
        return

    subpaths = _geometry(el, tag, flatness)
    if subpaths is None:
        if tag not in ("tspan",):
            unsupported.add(tag)
        return
    subpaths = [[_apply(mat, p) for p in sp] for sp in subpaths if len(sp) >= 2]
    if not subpaths:
        return

    fill = _colour(style.get("fill", "#000000"), gradients, art)
    if fill is not None and _num_or(style.get("fill-opacity"), 1.0) > 0.05:
        art.shapes.append(Shape(
            [sp for sp in subpaths if len(sp) >= 3],
            fill, style.get("fill-rule") == "evenodd", tag))

    stroke = _colour(style.get("stroke", "none"), gradients, art)
    if stroke is not None and _num_or(style.get("stroke-opacity"), 1.0) > 0.05:
        w = _num_or(style.get("stroke-width"), 1.0) * _scale_of(mat)
        if w > 0:
            quads = []
            closed = tag in ("rect", "circle", "ellipse", "polygon")
            cap = style.get("stroke-linecap", "butt")
            for sp in subpaths:
                quads += _stroke_to_fill(sp, w, closed or _is_closed(sp), cap)
            if quads:
                art.shapes.append(Shape(quads, stroke, False, tag + ":stroke"))


def _geometry(el, tag, flatness) -> list[list[Point]] | None:
    """Element to subpaths in its own user units, or None if unsupported."""
    g = el.get
    if tag == "path":
        return _path(g("d") or "", flatness)
    if tag == "rect":
        x, y = _len(g("x", "0")), _len(g("y", "0"))
        w, h = _len(g("width", "0")), _len(g("height", "0"))
        rx = _len(g("rx")) if g("rx") else (_len(g("ry")) if g("ry") else 0.0)
        ry = _len(g("ry")) if g("ry") else rx
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        if w <= 0 or h <= 0:
            return []
        if rx <= 0 or ry <= 0:
            return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
        pts = []
        n = max(4, int(math.pi / 2 / math.sqrt(2 * flatness / max(rx, ry, 1e-6))))
        for cx, cy, a0 in ((x + w - rx, y + h - ry, 0.0),
                           (x + rx, y + h - ry, math.pi / 2),
                           (x + rx, y + ry, math.pi),
                           (x + w - rx, y + ry, 3 * math.pi / 2)):
            for i in range(n + 1):
                a = a0 + (math.pi / 2) * i / n
                pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
        pts.append(pts[0])
        return [pts]
    if tag in ("circle", "ellipse"):
        cx, cy = _len(g("cx", "0")), _len(g("cy", "0"))
        if tag == "circle":
            rx = ry = _len(g("r", "0"))
        else:
            rx, ry = _len(g("rx", "0")), _len(g("ry", "0"))
        if rx <= 0 or ry <= 0:
            return []
        n = max(12, int(math.pi / math.sqrt(2 * flatness / max(rx, ry))))
        pts = [(cx + rx * math.cos(2 * math.pi * i / n),
                cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
        return [pts]
    if tag in ("polygon", "polyline"):
        nums = [float(v) for v in _NUM.findall(g("points", ""))]
        pts = list(zip(nums[0::2], nums[1::2]))
        if tag == "polygon" and pts:
            pts.append(pts[0])
        return [pts]
    if tag == "line":
        return [[(_len(g("x1", "0")), _len(g("y1", "0"))),
                 (_len(g("x2", "0")), _len(g("y2", "0")))]]
    return None


def _path(d: str, flatness: float) -> list[list[Point]]:
    """Flatten path data into polylines."""
    tokens = [t for t in _CMD.split(d) if t.strip()]
    subpaths: list[list[Point]] = []
    cur: list[Point] = []
    x = y = 0.0
    start = (0.0, 0.0)
    prev_c: Point | None = None
    prev_q: Point | None = None
    cmd = ""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if _CMD.fullmatch(tok):
            cmd = tok
            i += 1
            args = []
            if i < len(tokens) and not _CMD.fullmatch(tokens[i]):
                args = [float(v) for v in _NUM.findall(tokens[i])]
                i += 1
        else:
            args = [float(v) for v in _NUM.findall(tok)]
            i += 1
        rel = cmd.islower()
        c = cmd.upper()

        def take(n):
            for k in range(0, len(args) - n + 1, n):
                yield args[k:k + n]

        if c == "M":
            first = True
            for a in take(2):
                px, py = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                if first:
                    if len(cur) >= 2:
                        subpaths.append(cur)
                    cur = [(px, py)]
                    start = (px, py)
                    first = False
                else:
                    cur.append((px, py))
                x, y = px, py
            prev_c = prev_q = None
        elif c == "Z":
            if cur:
                cur.append(start)
                subpaths.append(cur)
                cur = [start]
                x, y = start
            prev_c = prev_q = None
        elif c in ("L", "H", "V"):
            n = {"L": 2, "H": 1, "V": 1}[c]
            for a in take(n):
                if c == "L":
                    x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                elif c == "H":
                    x = x + a[0] if rel else a[0]
                else:
                    y = y + a[0] if rel else a[0]
                cur.append((x, y))
            prev_c = prev_q = None
        elif c in ("C", "S"):
            n = 6 if c == "C" else 4
            for a in take(n):
                if c == "C":
                    p1 = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                    p2 = (x + a[2], y + a[3]) if rel else (a[2], a[3])
                    p3 = (x + a[4], y + a[5]) if rel else (a[4], a[5])
                else:
                    p1 = (2 * x - prev_c[0], 2 * y - prev_c[1]) if prev_c else (x, y)
                    p2 = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                    p3 = (x + a[2], y + a[3]) if rel else (a[2], a[3])
                _cubic(cur, (x, y), p1, p2, p3, flatness)
                x, y = p3
                prev_c, prev_q = p2, None
        elif c in ("Q", "T"):
            n = 4 if c == "Q" else 2
            for a in take(n):
                if c == "Q":
                    p1 = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                    p2 = (x + a[2], y + a[3]) if rel else (a[2], a[3])
                else:
                    p1 = (2 * x - prev_q[0], 2 * y - prev_q[1]) if prev_q else (x, y)
                    p2 = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                # A quadratic is a cubic with the control point pulled in.
                c1 = (x + 2 / 3 * (p1[0] - x), y + 2 / 3 * (p1[1] - y))
                c2 = (p2[0] + 2 / 3 * (p1[0] - p2[0]),
                      p2[1] + 2 / 3 * (p1[1] - p2[1]))
                _cubic(cur, (x, y), c1, c2, p2, flatness)
                x, y = p2
                prev_q, prev_c = p1, None
        elif c == "A":
            for a in take(7):
                p2 = (x + a[5], y + a[6]) if rel else (a[5], a[6])
                _arc(cur, (x, y), a[0], a[1], a[2], a[3] != 0, a[4] != 0, p2,
                     flatness)
                x, y = p2
            prev_c = prev_q = None
    if len(cur) >= 2:
        subpaths.append(cur)
    return subpaths


def _cubic(out, p0, p1, p2, p3, flatness, depth=0) -> None:
    """Flatten a cubic by subdividing until it is flat enough to be a line."""
    if depth > 16:
        out.append(p3)
        return
    ux, uy = p3[0] - p0[0], p3[1] - p0[1]
    n = math.hypot(ux, uy)
    if n < 1e-12:
        d = max(math.dist(p0, p1), math.dist(p0, p2))
    else:
        d = max(abs((p1[0] - p0[0]) * uy - (p1[1] - p0[1]) * ux) / n,
                abs((p2[0] - p0[0]) * uy - (p2[1] - p0[1]) * ux) / n)
    if d <= flatness:
        out.append(p3)
        return
    def mid(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    a1, a2, a3 = mid(p0, p1), mid(p1, p2), mid(p2, p3)
    b1, b2 = mid(a1, a2), mid(a2, a3)
    m = mid(b1, b2)
    _cubic(out, p0, a1, b1, m, flatness, depth + 1)
    _cubic(out, m, b2, a3, p3, flatness, depth + 1)


def _arc(out, p0, rx, ry, rot_deg, large, sweep, p1, flatness) -> None:
    """Elliptical arc, endpoint form, per the SVG implementation notes."""
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-12 or ry < 1e-12 or (abs(p1[0] - p0[0]) < 1e-12
                                    and abs(p1[1] - p0[1]) < 1e-12):
        out.append(p1)
        return
    phi = math.radians(rot_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    dx2, dy2 = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1 = cp * dx2 + sp * dy2
    y1 = -sp * dx2 + cp * dy2
    # Scale the radii up if they are too small to reach.
    lam = (x1 / rx) ** 2 + (y1 / ry) ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    k = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        k = -k
    cxp, cyp = k * rx * y1 / ry, -k * ry * x1 / rx
    cx = cp * cxp - sp * cyp + (p0[0] + p1[0]) / 2
    cy = sp * cxp + cp * cyp + (p0[1] + p1[1]) / 2

    def ang(ux, uy, vx, vy):
        d = (math.hypot(ux, uy) * math.hypot(vx, vy)) or 1e-12
        a = math.acos(max(-1.0, min(1.0, (ux * vx + uy * vy) / d)))
        return -a if ux * vy - uy * vx < 0 else a

    th0 = ang(1, 0, (x1 - cxp) / rx, (y1 - cyp) / ry)
    dth = ang((x1 - cxp) / rx, (y1 - cyp) / ry,
              (-x1 - cxp) / rx, (-y1 - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    n = max(2, int(abs(dth) / math.sqrt(2 * flatness / max(rx, ry)) / 2) + 2)
    for i in range(1, n + 1):
        t = th0 + dth * i / n
        ct, st = math.cos(t), math.sin(t)
        out.append((cx + cp * rx * ct - sp * ry * st,
                    cy + sp * rx * ct + cp * ry * st))


# --------------------------------------------------------------------------
# strokes, transforms, colours
# --------------------------------------------------------------------------

def _stroke_to_fill(pts: list[Point], w: float, closed: bool,
                    cap: str = "butt") -> list[list[Point]]:
    """A stroked polyline as a set of CCW quads and discs, unioned by nonzero."""
    h = w / 2
    out: list[list[Point]] = []
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy)
        if n < 1e-9:
            continue
        nx, ny = -dy / n * h, dx / n * h
        out.append(_ccw([(ax + nx, ay + ny), (bx + nx, by + ny),
                         (bx - nx, by - ny), (ax - nx, ay - ny)]))
    # Joins are discs. So are round caps; a square cap is the same disc's
    # bounding square, which is close enough at a nozzle's resolution.
    joints = list(pts) if (closed or cap in ("round", "square")) else pts[1:-1]
    if w > 1e-6:
        for (jx, jy) in joints:
            out.append(_ccw([(jx + h * math.cos(2 * math.pi * k / 10),
                              jy + h * math.sin(2 * math.pi * k / 10))
                             for k in range(10)]))
    return out


def _ccw(poly: list[Point]) -> list[Point]:
    return poly if _signed_area(poly) > 0 else poly[::-1]


def _signed_area(poly: list[Point]) -> float:
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return a / 2


def _transform(s: str | None):
    m = (1, 0, 0, 1, 0, 0)
    if not s:
        return m
    for name, body in re.findall(r"(\w+)\s*\(([^)]*)\)", s):
        a = [float(v) for v in _NUM.findall(body)]
        if name == "translate":
            t = (1, 0, 0, 1, a[0], a[1] if len(a) > 1 else 0)
        elif name == "scale":
            sx = a[0]
            sy = a[1] if len(a) > 1 else sx
            t = (sx, 0, 0, sy, 0, 0)
        elif name == "rotate":
            c, s_ = math.cos(math.radians(a[0])), math.sin(math.radians(a[0]))
            t = (c, s_, -s_, c, 0, 0)
            if len(a) >= 3:
                t = _mul(_mul((1, 0, 0, 1, a[1], a[2]), t),
                         (1, 0, 0, 1, -a[1], -a[2]))
        elif name == "matrix" and len(a) >= 6:
            t = tuple(a[:6])
        elif name == "skewX":
            t = (1, 0, math.tan(math.radians(a[0])), 1, 0, 0)
        elif name == "skewY":
            t = (1, math.tan(math.radians(a[0])), 0, 1, 0, 0)
        else:
            continue
        m = _mul(m, t)
    return m


def _mul(m, n):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2,
            a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def _apply(m, p):
    a, b, c, d, e, f = m
    return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)


def _scale_of(m) -> float:
    return math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) or 1.0


def _is_closed(sp: list[Point]) -> bool:
    return len(sp) > 2 and math.dist(sp[0], sp[-1]) < 1e-9


def _style_of(el) -> dict[str, str]:
    """Presentation attributes plus whatever the style attribute overrides."""
    out = {}
    for k in ("fill", "stroke", "stroke-width", "stroke-linecap",
              "fill-rule", "opacity",
              "fill-opacity", "stroke-opacity", "display", "visibility",
              "color"):
        v = el.get(k)
        if v is not None:
            out[k] = v.strip()
    for decl in (el.get("style") or "").split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _gradient_stops(root) -> dict[str, tuple[int, int, int]]:
    """Map each gradient id to its first stop colour, as a stand-in."""
    out = {}
    for el in root.iter():
        tag = el.tag.replace(SVG_NS, "")
        if tag in ("linearGradient", "radialGradient") and el.get("id"):
            for stop in el:
                st = _style_of(stop)
                raw = stop.get("stop-color") or st.get("stop-color")
                rgb = _parse_rgb(raw) if raw else None
                if rgb:
                    out[el.get("id")] = rgb
                    break
    return out


def _colour(raw: str | None, gradients, art) -> tuple[int, int, int] | None:
    if raw is None:
        return None
    raw = raw.strip()
    ref = re.match(r"url\(#([^)]+)\)", raw)
    if ref:
        rgb = gradients.get(ref.group(1))
        msg = ("gradients are flattened to their first stop"
               if rgb else f"cannot resolve paint {raw}; treated as black")
        if msg not in art.warnings:
            art.warnings.append(msg)
        return rgb or (0, 0, 0)
    return _parse_rgb(raw)


def _parse_rgb(raw: str) -> tuple[int, int, int] | None:
    raw = raw.strip().lower()
    if raw in NAMED:
        return NAMED[raw]
    if raw.startswith("#"):
        h = raw[1:]
        if len(h) == 3:
            return tuple(int(c * 2, 16) for c in h)
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        if len(h) in (4, 8):  # #rgba / #rrggbbaa
            n = len(h) // 4
            return tuple(int(h[i * n:(i + 1) * n] * (2 // n), 16) for i in range(3))
        return None
    m = re.match(r"rgba?\(([^)]*)\)", raw)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", ",").split(",")]
        vals = []
        for p in parts[:3]:
            vals.append(int(round(float(p[:-1]) * 2.55)) if p.endswith("%")
                        else int(round(float(p))))
        if len(vals) == 3:
            return tuple(max(0, min(255, v)) for v in vals)
    if raw in ("currentcolor",):
        return (0, 0, 0)
    return None


def _len(v: str | None, default: str = "0") -> float:
    """A length in user units. Percentages and odd units are not resolved."""
    if v is None:
        v = default
    m = _NUM.search(v)
    if not m:
        return 0.0
    n = float(m.group())
    unit = v[m.end():].strip().lower()
    return n * {"mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0,
                "pt": 96 / 72, "pc": 16.0}.get(unit, 1.0)


def _num_or(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_file(p, **kw) -> Art:
    """Load a file from disk. Local files are trusted; see :func:`load`."""
    from pathlib import Path
    kw.setdefault("limit", False)
    return load(Path(p).read_text(), **kw)
