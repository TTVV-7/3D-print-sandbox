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
from shapely.ops import unary_union

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

    return assemble(rings)


def assemble(rings):
    """Closed contours turned into filled shapes, by how deeply they nest.

    A ring inside another is a counter -- the hole in an O.  A ring inside
    *that* is not: it is ink again, the way the inner tube of a neon O is ink
    inside the hole inside the outer tube.  So the rule is the depth's parity
    rather than "contained by something": rings at an even depth are filled,
    rings at an odd depth are the holes cut out of the one they sit in.
    Monoton draws an O as eight concentric rings and Bungee Shade draws one as
    six; read as one ring with seven holes, which is what "contained" alone
    gives you, either comes out as a single self-crossing polygon that will
    not extrude.

    The cleaning matters as much as the nesting.  A display face is full of
    contours that touch or cross themselves, and a polygon built straight from
    one of those is invalid -- shapely will union it happily and then fail
    somewhere much later, inside a buffer or an extrude, with a message about
    a side location conflict.  So each ring is squared up with buffer(0)
    first, and the holes are taken out with a difference rather than handed to
    the Polygon constructor, which keeps every shape out of here valid.
    """
    polys = [Polygon(r).buffer(0) for r in rings]
    live = [i for i, q in enumerate(polys) if not q.is_empty and q.area > 0]

    def inside(i, j):
        """Is ring i inside ring j?  By how much of i lies in j, not by
        contains().

        A counter and the letter round it often share an edge, and a strict
        contains() says no to that, which leaves the hole in a Pacifico e
        filled.  A single point says yes to too much instead: in a script the
        letters overlap, and the c after a b has a point inside the b without
        being its counter.  All but a whisker of i, and the answer is right
        both times.  The cheap tests come first because this runs on every
        pair of contours in the string.
        """
        a, b = polys[i], polys[j]
        if b.area <= a.area:
            return False
        ax0, ay0, ax1, ay1 = a.bounds
        bx0, by0, bx1, by1 = b.bounds
        if ax0 < bx0 or ay0 < by0 or ax1 > bx1 or ay1 > by1:
            return False
        return a.intersection(b).area >= 0.99 * a.area

    depth = {i: sum(1 for j in live if j != i and inside(i, j)) for i in live}

    shapes = []
    for i in live:
        if depth[i] % 2:
            continue                       # this ring is somebody's counter
        kids = [polys[j] for j in live if depth[j] == depth[i] + 1 and inside(j, i)]
        piece = polys[i].difference(unary_union(kids)) if kids else polys[i]
        shapes.extend(g for g in getattr(piece, "geoms", [piece]) if g.area > 0)
    return shapes


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
