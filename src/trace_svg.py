"""Trace an SVG logo into outline JSON that logos.py can use.

Every closed subpath of every <path> becomes a polygon and they are combined
under the even-odd rule, which is just an XOR of the subpaths -- each ring
toggles inside/outside, so arbitrarily nested rings (Ford's oval is four deep:
rim, white ring, navy field, lettering) come out right.

The result is split into a "pad" -- the outermost boundary, solid -- and the
"cuts", everything the fill leaves hollow inside it.  That is how a badge is
drawn: a solid field with the lettering and rings knocked out of it, which is
also exactly what generate.py wants for a raised pad with cut-through strokes.

Usage:  python3 src/trace_svg.py logo.svg src/ford_script.json
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
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
