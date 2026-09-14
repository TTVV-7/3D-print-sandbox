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
