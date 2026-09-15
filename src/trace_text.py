"""Trace a string from a TTF into outline polygons.

Glyph outlines come straight out of the font as curves and are flattened to
polygons -- no rasterising and re-tracing, so the edges stay clean.

A character the chosen face has no glyph for can come from a `fallback` face
instead, scaled to stand as tall as a capital and sit on the same baseline.
That is how an emoji gets into a line of lettering, and it only works with a
*monochrome* emoji font: the colour ones (Noto Color Emoji and friends) store
bitmaps, which have no outline to extrude.  src/fonts/NotoEmoji-Bold.ttf is
the one to hand in.

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


# Characters that carry no outline of their own and are dropped rather than
# looked up: the variation selectors that say "draw the last one as text or as
# emoji", the zero-width joiner that welds 👨 + 👩 into a family, and the
# skin-tone modifiers.  A ZWJ sequence comes out as its separate pieces, which
# is the best a per-codepoint tracer can do and better than refusing the line.
PASS_OVER = {0xFE0E, 0xFE0F, 0x200D}
SKIN_TONES = range(0x1F3FB, 0x1F400)

_FACES = {}


def face(path):
    """(glyphset, cmap, units per em) for a font file, opened once.

    The app rebuilds on every keystroke and a TTF takes long enough to parse
    that doing it per build is felt, so the parsed face is kept.
    """
    if path not in _FACES:
        font = TTFont(path)
        _FACES[path] = (font.getGlyphSet(), font.getBestCmap(),
                        font["head"].unitsPerEm)
    return _FACES[path]


def contours(glyphset, name):
    pen = Flattener(glyphset)
    glyphset[name].draw(pen)
    return pen.contours


def cap_em(path):
    """Height of a capital H in em: what a fallback glyph is scaled to match."""
    glyphset, cmap, upem = face(path)
    name = cmap.get(ord("H"))
    ys = [y for c in (contours(glyphset, name) if name else []) for _, y in c]
    return max(ys) / upem if ys else 0.7


def rings_of(text, font_path, tracking=0.0, fallback=None):
    """Closed contours for `text`, in em, baseline on y=0 and starting at x=0.

    Anything the face has no glyph for is taken from `fallback` -- scaled so
    that it stands as tall as a capital of the face it is sitting in, which is
    what keeps an emoji from towering over the word it is next to -- and is an
    error when there is no fallback or it has no glyph either.
    """
    glyphset, cmap, upem = face(font_path)
    spare = face(fallback) if fallback else None
    cap = cap_em(font_path) if spare else 0.0

    out, x = [], 0.0                         # x in em of the finished line
    for ch in text:
        cp = ord(ch)
        if cp in PASS_OVER or cp in SKIN_TONES:
            continue
        name = cmap.get(cp)
        if name is not None:
            k = 1.0 / upem
            cs = contours(glyphset, name)
            advance = glyphset[name].width * k
        elif spare and spare[1].get(cp) is not None:
            f_glyphs, f_cmap, f_upem = spare
            f_name = f_cmap.get(cp)
            cs = contours(f_glyphs, f_name)
            top = max((y for c in cs for _, y in c), default=f_upem) / f_upem
            # An emoji glyph fills its em; a capital is about 0.7 of one.  Scaling
            # on the glyph's own height rather than its em is what lines the top
            # of the flame up with the top of the K next to it.
            k = (cap / top if top > 0 else 1.0) / f_upem
            advance = f_glyphs[f_name].width * k
        else:
            raise ValueError(f"{Path(font_path).name} has no glyph for {ch!r}"
                             + ("" if spare else " -- and no fallback face was given"))
        for c in cs:
            out.append([(px * k + x, py * k) for px, py in c])
        x += advance + tracking
    return out


def trace(text, font_path, tracking=0.0, fallback=None):
    """Outlines for `text`, in em units, baseline on y=0 and starting at x=0.

    `tracking` is extra letterspacing, also in em -- cards.py opens up small
    lettering with it, which both reads better and widens the gaps between
    strokes, so more of them survive the nozzle.
    """
    rings = rings_of(text, font_path, tracking, fallback)

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

    # Letterforms come out of a font clean, but an emoji is drawn as a stack of
    # overlapping pieces and lands here self-intersecting about half the time.
    # buffer(0) is the standard repair; it leaves a valid polygon alone.
    out = []
    for s in shapes:
        s = s if s.is_valid else s.buffer(0)
        parts = s.geoms if s.geom_type == "MultiPolygon" else [s]
        out += [g for g in parts if g.geom_type == "Polygon" and g.area > 1e-9]
    return out


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
