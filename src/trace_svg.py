"""Trace an SVG logo into outline JSON that logos.py can use.

Every closed subpath of every <path> becomes a polygon and they are combined
under the even-odd rule, which is just an XOR of the subpaths -- each ring
toggles inside/outside, so arbitrarily nested rings (Ford's oval is four deep:
rim, white ring, navy field, lettering) come out right.

The result is split into a "pad" -- the outermost boundary, solid -- and the
"cuts", everything the fill leaves hollow inside it.  That is how a badge is
drawn: a solid field with the lettering and rings knocked out of it, which is
also exactly what generate.py wants for a raised pad with cut-through strokes.

shapes() is the other reading of the same file, for cards.py: the filled
geometry as it would render, rather than a pad with cuts.

Usage:  python3 src/trace_svg.py logo.svg src/ford_script.json
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union
from svgpathtools import parse_path

SAMPLES = 220   # points per subpath; the curves are short, this is plenty


def subpath_polygons(d):
    polys = []
    for sub in parse_path(d).continuous_subpaths():
        t = np.linspace(0, 1, SAMPLES, endpoint=False)
        pts = [sub.point(x) for x in t]
        ring = [(p.real, -p.imag) for p in pts]      # SVG y runs down
        poly = Polygon(ring).buffer(0)
        if poly.geom_type == "Polygon" and poly.area > 0:
            polys.append(poly)
    return polys


def element_polygons(el):
    """The polygons of one drawable element, whatever it is."""
    tag = el.tag.rsplit("}", 1)[-1]
    g = lambda k, d="0": float(el.get(k, d))
    if tag == "path" and el.get("d"):
        return subpath_polygons(el.get("d"))
    if tag == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        return [box(x, -(y + h), x + w, -y)]
    if tag == "circle":
        return [Point(g("cx"), -g("cy")).buffer(g("r"), quad_segs=48)]
    if tag == "ellipse":
        e = Point(0, 0).buffer(1.0, quad_segs=48)
        from shapely import affinity
        return [affinity.translate(affinity.scale(e, g("rx"), g("ry"), origin=(0, 0)),
                                   g("cx"), -g("cy"))]
    if tag == "polygon" and el.get("points"):
        nums = [float(v) for v in el.get("points").replace(",", " ").split()]
        poly = Polygon([(nums[i], -nums[i + 1]) for i in range(0, len(nums) - 1, 2)]).buffer(0)
        return [poly] if poly.area > 0 else []
    return []


NAMED = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000",
    "blue": "#0000ff", "yellow": "#ffff00", "orange": "#ffa500", "gray": "#808080",
    "grey": "#808080", "silver": "#c0c0c0", "navy": "#000080", "gold": "#ffd700",
    "purple": "#800080", "teal": "#008080", "maroon": "#800000", "lime": "#00ff00",
    "cyan": "#00ffff", "aqua": "#00ffff", "magenta": "#ff00ff", "fuchsia": "#ff00ff",
    "darkgray": "#a9a9a9", "darkgrey": "#a9a9a9", "lightgray": "#d3d3d3",
    "lightgrey": "#d3d3d3", "dimgray": "#696969", "dimgrey": "#696969",
}


def parse_colour(value):
    """An SVG colour as '#rrggbb', or None for anything that is not a plain
    colour -- 'none', a gradient reference, currentColor."""
    if not value:
        return None
    v = value.strip().lower()
    if v in ("none", "transparent", "currentcolor", "inherit") or v.startswith("url("):
        return None
    if v in NAMED:
        return NAMED[v]
    if v.startswith("#"):
        h = v[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h[:3])
        if len(h) in (6, 8) and all(c in "0123456789abcdef" for c in h[:6]):
            return "#" + h[:6]
        return None
    if v.startswith("rgb"):
        nums = v[v.index("(") + 1:v.rindex(")")].replace("/", ",").split(",")[:3]
        try:
            chan = [round(float(n.strip().rstrip("%")) * (2.55 if "%" in n else 1.0))
                    for n in nums]
        except ValueError:
            return None
        return "#%02x%02x%02x" % tuple(max(0, min(255, c)) for c in chan)
    return None


def fill_of(el, inherited):
    """The fill an element paints with: its own attribute or style, else
    what it inherits.  'none' is kept distinct from 'not stated'."""
    value = el.get("fill")
    style = el.get("style") or ""
    for decl in style.split(";"):
        k, _, v = decl.partition(":")
        if k.strip() == "fill":
            value = v.strip()
    if value is None:
        return inherited
    return "none" if value.strip().lower() == "none" else parse_colour(value)


def shapes(svg, fills=False):
    """The filled geometry of an SVG logo, as a list of polygons, y up.

    Within one element the subpaths are combined even-odd, which is how a
    letter gets its counter and a house its door.  Between elements they are
    *unioned*: two paths that overlap almost always mean "and", and reading
    them even-odd would punch a hole where they cross.  Transforms are not
    applied -- flatten the file first if it has them.  `svg` is a path, or the
    file's text.

    With fills=True the result is [(fill, [polygons]), ...] instead, one
    entry per distinct fill colour ('#rrggbb', or None where none was
    stated), each merged the same way -- so a design drawn in several
    colours can be printed in several.  Elements filled 'none' are skipped.
    """
    text = svg if svg.lstrip().startswith("<") else Path(svg).read_text()
    root = ET.fromstring(text)
    groups = {}

    def walk(el, inherited):
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("defs", "clipPath", "mask", "symbol", "pattern", "marker"):
            return
        fill = fill_of(el, inherited)
        if fill != "none":
            polys = sorted(element_polygons(el), key=lambda p: -p.area)
            if polys:
                shape = polys[0]
                for p in polys[1:]:
                    shape = shape.symmetric_difference(p)
                groups.setdefault(fill, []).append(shape)
        for child in el:
            walk(child, fill)

    walk(root, None)
    if not groups:
        raise ValueError("no paths, rects, circles or polygons in that SVG")

    def merge(filled):
        merged = unary_union(filled)
        parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        return [p for p in parts if p.area > 1e-9]

    if fills:
        return [(fill, merge(filled)) for fill, filled in groups.items()]
    return merge([s for filled in groups.values() for s in filled])


# ---------------------------------------------------------------------------
# painted(): the SVG as it looks, for a logo that *is* the part
# ---------------------------------------------------------------------------
# shapes() is enough for artwork drawn the way a stencil wants it.  A company
# logo off a website is rarely that: it is nested groups with transforms on
# them, fills set by a CSS class in a <style> block, strokes, and colours
# painted on top of each other -- a white letter drawn over a red disc, which
# is a red disc with a letter-shaped hole in it and a white letter in the hole.
# painted() reads all of that and hands back what you would see.

def _numbers(text):
    import re
    return [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", text)]


def parse_transform(text):
    """An SVG transform list as a 2x3 affine (a, b, c, d, e, f), meaning
    x' = a x + c y + e, y' = b x + d y + f -- SVG's own matrix() order."""
    import re
    m = np.eye(3)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = _numbers(args)
        t = np.eye(3)
        if name == "matrix" and len(v) == 6:
            t = np.array([[v[0], v[2], v[4]], [v[1], v[3], v[5]], [0, 0, 1]])
        elif name == "translate" and v:
            t[0, 2], t[1, 2] = v[0], (v[1] if len(v) > 1 else 0.0)
        elif name == "scale" and v:
            t[0, 0], t[1, 1] = v[0], (v[1] if len(v) > 1 else v[0])
        elif name == "rotate" and v:
            a = np.radians(v[0])
            r = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
            if len(v) == 3:
                to = np.array([[1, 0, v[1]], [0, 1, v[2]], [0, 0, 1]])
                back = np.array([[1, 0, -v[1]], [0, 1, -v[2]], [0, 0, 1]])
                r = to @ r @ back
            t = r
        elif name == "skewX" and v:
            t[0, 1] = np.tan(np.radians(v[0]))
        elif name == "skewY" and v:
            t[1, 0] = np.tan(np.radians(v[0]))
        m = m @ t
    return m


def _css(root):
    """{selector: {property: value}} from every <style> block, for the plain
    selectors an exported logo uses: .class, #id and bare element names,
    comma-separated.  Anything fancier is ignored."""
    import re
    rules = {}
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "style" or not el.text:
            continue
        text = re.sub(r"/\*.*?\*/", "", el.text, flags=re.S)
        for sels, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
            decls = {}
            for decl in body.split(";"):
                k, _, v = decl.partition(":")
                if k.strip():
                    decls[k.strip().lower()] = v.strip()
            for sel in sels.split(","):
                rules.setdefault(sel.strip(), {}).update(decls)
    return rules


def _style(el, rules):
    """Every presentation property set on the element itself: attribute, then
    CSS rules by element, class and id, then the style attribute -- the
    cascade order that matters for an exported file."""
    tag = el.tag.rsplit("}", 1)[-1]
    out = {}
    for k in ("fill", "stroke", "stroke-width", "opacity", "fill-opacity",
              "stroke-opacity", "display", "visibility", "fill-rule"):
        if el.get(k) is not None:
            out[k] = el.get(k)
    out.update(rules.get(tag, {}))
    for cls in (el.get("class") or "").split():
        out.update(rules.get("." + cls, {}))
    if el.get("id"):
        out.update(rules.get("#" + el.get("id"), {}))
    for decl in (el.get("style") or "").split(";"):
        k, _, v = decl.partition(":")
        if k.strip():
            out[k.strip().lower()] = v.strip()
    return out


def _raw(el):
    """An element's polygons in its own SVG coordinates, y down, plus its
    outline as lines, for a stroke.  element_polygons() flips y; this undoes
    that so the transform can be applied the way the file means it."""
    from shapely import affinity
    from shapely.geometry import LineString
    tag = el.tag.rsplit("}", 1)[-1]
    flip = lambda g: affinity.scale(g, 1, -1, origin=(0, 0))
    lines = []
    if tag == "path" and el.get("d"):
        polys = []
        for sub in parse_path(el.get("d")).continuous_subpaths():
            t = np.linspace(0, 1, SAMPLES, endpoint=not sub.isclosed())
            pts = [(p.real, p.imag) for p in (sub.point(x) for x in t)]
            if len(pts) > 1:
                lines.append(LineString(pts + ([pts[0]] if sub.isclosed() else [])))
            if len(pts) > 2:
                poly = Polygon(pts).buffer(0)
                if not poly.is_empty and poly.area > 0:
                    polys.extend(getattr(poly, "geoms", [poly]))
        return polys, lines
    if tag in ("line", "polyline"):
        if tag == "line":
            g = lambda k: float(el.get(k, "0"))
            lines = [LineString([(g("x1"), g("y1")), (g("x2"), g("y2"))])]
        else:
            v = _numbers(el.get("points") or "")
            pts = list(zip(v[::2], v[1::2]))
            lines = [LineString(pts)] if len(pts) > 1 else []
        return [], lines
    if tag == "rect" and (el.get("rx") or el.get("ry")):
        g = lambda k, d="0": float((el.get(k) or d).rstrip("px") or 0)
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        r = min(g("rx", el.get("ry") or "0"), w / 2, h / 2)
        polys = [box(x + r, y + r, x + w - r, y + h - r).buffer(r, quad_segs=24)
                 if r > 0 else box(x, y, x + w, y + h)]
        return polys, [p.exterior for p in polys]
    polys = [flip(p) for p in element_polygons(el)]
    return polys, [p.exterior for p in polys]


def painted(svg, keep_background=True, report=None):
    """[(fill, geometry)] for an SVG, as it is seen: y up, transforms applied,
    fills and strokes both, each colour's region with whatever was painted
    over it later taken out.  `fill` is '#rrggbb'; anything unstated paints
    black, which is what a browser does.

    With keep_background=False, a first shape that covers everything else --
    the white or coloured rectangle a logo is so often exported on -- is left
    out, so the logo's own outline is what is left.  Its colour goes in
    report["background"], if a `report` dict is handed in.
    """
    from shapely import affinity
    text = svg if svg.lstrip().startswith("<") else Path(svg).read_text()
    root = ET.fromstring(text)
    rules = _css(root)
    order = []                      # (fill, geometry) as painted

    def paint(colour, geom):
        if colour and not geom.is_empty and geom.area > 0:
            order.append((colour, geom))

    def walk(el, ctm, inherited):
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("defs", "clipPath", "mask", "symbol", "pattern", "marker", "style",
                   "title", "desc", "metadata", "linearGradient", "radialGradient", "text"):
            return
        own = _style(el, rules)
        if own.get("display", "").strip() == "none":
            return
        style = {**inherited, **{k: v for k, v in own.items() if k != "opacity"}}
        try:
            opacity = inherited.get("_opacity", 1.0) * float(own.get("opacity", 1))
        except ValueError:
            opacity = inherited.get("_opacity", 1.0)
        style["_opacity"] = opacity
        ctm = ctm @ parse_transform(el.get("transform"))
        if opacity > 0.05 and style.get("visibility", "visible") != "hidden":
            polys, lines = _raw(el)
            a, c, e = ctm[0]
            b, d, f = ctm[1]
            place = lambda g: affinity.scale(affinity.affine_transform(g, [a, c, b, d, e, f]),
                                             1, -1, origin=(0, 0))
            fill = style.get("fill", "#000000")
            fill = None if (fill or "").strip().lower() == "none" else parse_colour(fill)
            try:
                fill_op = float(style.get("fill-opacity", 1))
            except ValueError:
                fill_op = 1.0
            if polys and fill and fill_op > 0.05:
                polys.sort(key=lambda p: -p.area)
                shape = polys[0]
                for p in polys[1:]:
                    shape = shape.symmetric_difference(p)
                paint(fill, place(shape))
            stroke = parse_colour(style.get("stroke"))
            try:
                width = float(_numbers(style.get("stroke-width", "1"))[0])
            except (IndexError, ValueError):
                width = 1.0
            if stroke and lines and width > 0:
                scale = np.sqrt(abs(np.linalg.det(ctm[:2, :2]))) or 1.0
                band = unary_union([place(l) for l in lines]).buffer(
                    width * scale / 2.0, quad_segs=12)
                paint(stroke, band)
        for child in el:
            walk(child, ctm, style)

    walk(root, np.eye(3), {})
    if not order:
        raise ValueError("nothing filled or stroked in that SVG -- text has to be "
                         "converted to outlines first")

    if not keep_background and len(order) > 1:
        first = order[0][1]
        rest = unary_union([g for _, g in order[1:]])
        # A backdrop: the first thing painted, nearly its own bounding box,
        # and everything after it inside it.
        x0, y0, x1, y1 = first.bounds
        boxy = first.area >= 0.9 * (x1 - x0) * (y1 - y0)
        if boxy and rest.difference(first).area <= 0.02 * rest.area:
            if report is not None:
                report["background"] = order[0][0]
            order = order[1:]

    regions = {}
    for colour, geom in order:
        for k in regions:
            if k != colour:
                regions[k] = regions[k].difference(geom)
        regions[colour] = regions[colour].union(geom) if colour in regions else geom
    return [(k, g) for k, g in regions.items() if not g.is_empty and g.area > 0]


def trace(svg_path):
    root = ET.parse(svg_path).getroot()
    polys = []
    for el in root.iter():
        if el.tag.endswith("path") and el.get("d"):
            polys.extend(subpath_polygons(el.get("d")))
    polys.sort(key=lambda p: -p.area)

    filled = polys[0]
    for p in polys[1:]:
        filled = filled.symmetric_difference(p)      # even-odd

    pad = Polygon(polys[0].exterior)                  # outermost boundary, solid
    cuts = pad.difference(filled)
    cuts = list(cuts.geoms) if cuts.geom_type == "MultiPolygon" else [cuts]
    return pad, [c for c in cuts if c.area > 1e-9]


def ring(poly):
    return [list(map(float, c)) for c in poly.exterior.coords]


def main(svg_path, out):
    pad, cuts = trace(svg_path)
    data = {
        "source": Path(svg_path).name,
        "pad": {"exterior": ring(pad),
                "holes": [[list(map(float, c)) for c in r.coords] for r in pad.interiors]},
        "cuts": [{"exterior": ring(c),
                  "holes": [[list(map(float, c2)) for c2 in r.coords] for r in c.interiors]}
                 for c in cuts],
    }
    Path(out).write_text(json.dumps(data))
    b = pad.bounds
    print(f"{out}: pad {b[2]-b[0]:.3f} x {b[3]-b[1]:.3f}, {len(cuts)} cut shapes")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
