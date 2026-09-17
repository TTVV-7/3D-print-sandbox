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
from svgpathtools import CubicBezier, Line, QuadraticBezier, parse_path

# How far the flattened outline may stray from the real curve, as a fraction
# of the artwork's own diagonal.  On a 120 mm plate this is about three
# hundredths of a millimetre -- a thirteenth of a nozzle, well under a layer,
# and past the point where anything is gained by asking for more vertices.
#
# It replaces a flat budget of 220 points per subpath, which was fine for the
# line-art logos this file was written for and quietly terrible for anything
# traced.  A fixed budget spends the same points on a gentle sweep as on a
# row of fine detail, so the error grew with the detail in the artwork: on a
# 120 mm plate, 0.06 mm for a plain blob, 0.38 mm once it had two dozen
# lobes, 0.93 mm at four dozen -- two nozzles wide, and visible as flats and
# big triangles across every curve.  Subdividing by curvature instead holds
# the error at about 0.02 mm whatever is thrown at it.
TOLERANCE = 1 / 4000

# A curve that has not converged by here is not going to.  Twelve halvings is
# four thousand points for one segment, which no real artwork needs.
MAX_DEPTH = 12


# Where a segment that is not a Bezier is probed for straightness.  Not the
# midpoint alone: an S-shaped curve crosses its own chord in the middle, so a
# midpoint test calls it flat and leaves the bulge either side of the crossing
# as one straight line.
PROBES = (0.2, 0.4, 0.5, 0.6, 0.8)

# A cubic sits inside the hull of its four control points, and its greatest
# departure from the chord is at most three quarters of its control points'.
# Measuring the controls instead of sampling the curve is the difference
# between a bound and a guess: sampling can miss a bulge between the samples,
# and on a path of S-curves it does.
HULL = 0.75


def straying(seg, tol):
    """How far `seg` may stray from the straight line between its ends.

    An upper bound, not an estimate.  For the Beziers -- which is what an SVG
    is almost entirely made of -- it comes from the control points and is
    therefore certain.  Anything else, an elliptical arc in practice, is
    probed along its length.
    """
    a, b = seg.point(0.0), seg.point(1.0)
    span = abs(b - a)

    def off(p):
        # Distance from a point to the chord.  A segment that ends where it
        # started has no chord to measure against, so measure from the start.
        if span < 1e-12:
            return abs(p - a)
        return abs(((b - a).conjugate() * (p - a)).imag) / span

    if isinstance(seg, Line):
        return 0.0
    if isinstance(seg, CubicBezier):
        return HULL * max(off(seg.control1), off(seg.control2))
    if isinstance(seg, QuadraticBezier):
        return HULL * off(seg.control)
    return max(off(seg.point(t)) for t in PROBES)


def flatten(seg, tol, depth=0):
    """The start of `seg` plus enough points along it to stay within `tol`.

    Curves are subdivided where they actually bend rather than sampled at a
    fixed rate, which is the difference between a circle and a dodecagon: a
    long gentle sweep costs a handful of points and a tight corner gets as
    many as it needs.  The test is how far the curve strays from the straight
    line between its ends; under the tolerance the line is the curve as far as
    anyone printing it is concerned, and over it, halve and ask again.

    A straight line answers on the first test and costs one point, so a path
    made of lines stays exactly as cheap as it was.
    """
    if depth >= MAX_DEPTH or straying(seg, tol) <= tol:
        return [seg.point(0.0)]
    return (flatten(seg.cropped(0.0, 0.5), tol, depth + 1)
            + flatten(seg.cropped(0.5, 1.0), tol, depth + 1))


def subpath_polygons(d):
    polys = []
    for sub in parse_path(d).continuous_subpaths():
        x0, x1, y0, y1 = sub.bbox()
        tol = max(np.hypot(x1 - x0, y1 - y0) * TOLERANCE, 1e-9)
        pts = []
        for seg in sub:
            pts.extend(flatten(seg, tol))
        ring = [(p.real, -p.imag) for p in pts]      # SVG y runs down
        if len(ring) < 3:
            continue
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
