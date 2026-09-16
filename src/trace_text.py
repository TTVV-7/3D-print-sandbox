"""Trace a string from a TTF into outline JSON that logos.py can use.

Glyph outlines come straight out of the font as curves and are flattened to
polygons -- no rasterising and re-tracing, so the edges stay clean.

Usage:  python3 src/trace_text.py FORD /path/to/Font.ttf src/ford_wordmark.json
"""
import json
import sys
from pathlib import Path

import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely.geometry import Polygon

FLATTEN = 12  # segments per curve


class Flattener(BasePen):
    """Collects closed contours as point lists, flattening cubics."""

    def __init__(self, glyphset):
        super().__init__(glyphset)
        self.contours, self._cur = [], []

    def _moveTo(self, pt):
        self._cur = [pt]

    def _lineTo(self, pt):
        self._cur.append(pt)

    def _curveToOne(self, c1, c2, pt):
        p0 = np.array(self._cur[-1], float)
        pts = np.array([c1, c2, pt], float)
        t = np.linspace(0, 1, FLATTEN + 1)[1:, None]
        self._cur.extend(
            ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * pts[0]
             + 3 * (1 - t) * t ** 2 * pts[1] + t ** 3 * pts[2]).tolist())

    def _closePath(self):
        if len(self._cur) > 2:
            self.contours.append(self._cur)
        self._cur = []


def trace(text, font_path, tracking=0.0):
    """Outlines for `text`, in em units, baseline on y=0 and starting at x=0.

    `tracking` is extra letterspacing, also in em -- cards.py opens up small
    lettering with it, which both reads better and widens the gaps between
    strokes, so more of them survive the nozzle.
    """
    font = TTFont(font_path)
    glyphset = font.getGlyphSet()
    cmap = font.getBestCmap()
    upem = font["head"].unitsPerEm

    rings, x = [], 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            raise ValueError(f"{Path(font_path).name} has no glyph for {ch!r}")
        pen = Flattener(glyphset)
        glyphset[name].draw(pen)
        for c in pen.contours:
            rings.append([((px + x) / upem, py / upem) for px, py in c])
        x += glyphset[name].width + tracking * upem

    # Nesting, by depth rather than by "is it inside anything".  A ring inside
    # another is a counter; a ring inside *that* is an island standing in the
    # counter and is solid again -- the pip in the bowl of an ornamented
    # Victorian P, the inner line of an inline face, the whole construction of
    # a shadowed one.  Counting only one level deep gets those wrong twice
    # over: the island is dropped, and it is also handed to the outermost ring
    # as a second hole inside the first, which is the "holes are nested"
    # polygon that no boolean will touch.  So each ring is given the smallest
    # ring that contains it as its parent; even depth is ink, odd depth is a
    # hole in the ring above it.
    polys = [Polygon(r).buffer(0) for r in rings]
    parent = []
    for i, p in enumerate(polys):
        inside = [j for j, q in enumerate(polys)
                  if i != j and q.area > p.area and q.contains(p)]
        parent.append(min(inside, key=lambda j: polys[j].area) if inside else None)

    def depth(i):
        d = 0
        while parent[i] is not None:
            i, d = parent[i], d + 1
        return d

    shapes = []
    for i, ring in enumerate(rings):
        if depth(i) % 2:
            continue                       # this ring is somebody's counter
        holes = [rings[j] for j, up in enumerate(parent) if up == i]
        shapes += valid(Polygon(ring, holes))
    return shapes


def valid(poly):
    """`poly` as a list of polygons a boolean will accept.

    Usually that is the one it was given.  Some faces are drawn with a contour
    that crosses back over itself, which a rasteriser fills without complaint
    and is therefore a drawing that ships: the rough display faces are full of
    them, where an outline has been roughened by hand and a barb has been
    dragged back through the stem.  A boolean is not a rasteriser.  Handed one
    of those it raises rather than returns, several steps further down where
    the outline is long since anonymous, so it is settled here instead, into
    the shape the rasteriser would have shown -- and a glyph that comes apart
    into two pieces is two pieces.
    """
    if poly.is_valid:
        return [poly]
    fixed = poly.buffer(0)
    if fixed.is_empty:
        return []
    return [g for g in getattr(fixed, "geoms", [fixed]) if g.geom_type == "Polygon"]


def main(text, font_path, out):
    shapes = trace(text, font_path)
    data = {
        "text": text,
        "font": Path(font_path).name,
        "shapes": [{"exterior": [list(map(float, c)) for c in s.exterior.coords],
                    "holes": [[list(map(float, c)) for c in r.coords] for r in s.interiors]}
                   for s in shapes],
    }
    Path(out).write_text(json.dumps(data, indent=1))
    b = np.array([s.bounds for s in shapes])
    print(f"{out}: {len(shapes)} glyphs, "
          f"{b[:, 2].max() - b[:, 0].min():.3f} x {b[:, 3].max() - b[:, 1].min():.3f} em")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
