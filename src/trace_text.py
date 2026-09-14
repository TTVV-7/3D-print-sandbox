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

    # A ring contained by another is a counter, not a separate letter.
    polys = [Polygon(r).buffer(0) for r in rings]
    shapes = []
    for i, p in enumerate(polys):
        holes = [rings[j] for j, q in enumerate(polys)
                 if i != j and p.contains(q) and p.area > q.area]
        if any(polys[j].contains(p) and polys[j].area > p.area
               for j in range(len(polys)) if j != i):
            continue                       # this ring is somebody's counter
        shapes.append(Polygon(rings[i], holes))
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
