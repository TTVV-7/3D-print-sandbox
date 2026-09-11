"""Emblem outlines, as flat shapely geometry centred on the origin.

Each builder returns a *list* of simple, individually valid polygons -- the
strokes of the mark -- normalised so the overall width is 2.0; generate.py
rescales to millimetres, extrudes each stroke and lets the boolean engine weld
them together.  Handing shapely a unary_union of the strokes instead looks
tidier but produces boundaries that touch themselves at the points where
strokes meet, and extruding that comes out non-watertight.

The round marks (BMW, Mercedes, Toyota) are constructed from primitives rather
than traced from a mesh, so the symmetry is exact and every stroke width is a
tunable number -- which matters, because stroke width is what decides whether
the logo survives a 0.4 mm nozzle.
"""
import json
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

OUTLINE = Path(__file__).resolve().parent / "logo_outline.json"
QUAD = 64  # arc resolution


def _circle(r):
    return Point(0.0, 0.0).buffer(r, quad_segs=QUAD)


def _ellipse(cx, cy, rx, ry):
    e = affinity.scale(_circle(1.0), rx, ry, origin=(0, 0))
    return affinity.translate(e, cx, cy)


def _ring(outer, thickness):
    """True uniform-width outline of `outer` (buffer, not a scaled copy)."""
    return outer.difference(outer.buffer(-thickness))


def _wedge(r, a0, a1):
    ang = np.radians(np.linspace(a0, a1, 64))
    pts = [(0.0, 0.0)] + [(r * np.cos(t), r * np.sin(t)) for t in ang]
    return Polygon(pts)


def _dedupe(poly, tol=1e-9):
    """Drop consecutive near-duplicate vertices.

    Shapely happily calls a ring with a repeated point valid, but earcut turns
    it into a degenerate triangle and the extrusion comes out non-watertight.
    """
    def ring(coords):
        out = [coords[0]]
        for c in coords[1:]:
            if abs(c[0] - out[-1][0]) > tol or abs(c[1] - out[-1][1]) > tol:
                out.append(c)
        return out

    return Polygon(ring(list(poly.exterior.coords)),
                   [ring(list(r.coords)) for r in poly.interiors])


def honda():
    """Traced from the supplied honda_logo.glb by extract_outline.py."""
    data = json.loads(OUTLINE.read_text())
    poly = Polygon(data["exterior"], data["holes"]).buffer(0)
    k = 2.0 / data["width"]
    return [affinity.scale(poly, k, k, origin=(0, 0))]


def bmw():
    """Roundel: outer band plus the two diagonally opposite quarters.

    Printed with a filament change, the raised parts come out in the second
    colour and the two recessed quarters stay in the first -- which is the
    roundel.  The quarters only meet at a point, so a small hub ties them
    together into one printable island.  (No 'BMW' lettering in the band: at
    13 mm across it would be under a millimetre tall.)
    """
    band_t = 0.155
    band = _ring(_circle(1.0), band_t)
    # Quarters run slightly into the band so the strokes overlap rather than
    # merely abut.  Built as wedges directly: cutting a circle with a wedge
    # instead leaves a duplicate vertex where the cut crosses an axis.
    r_q = 1.0 - band_t + 0.03
    quarters = [_wedge(r_q, a0, a0 + 90) for a0 in (0, 180)]
    return [band, *quarters, _circle(0.09)]


def mercedes():
    """Three-pointed star in a ring: three radial bars meeting at the centre."""
    band_t = 0.115
    r_i = 1.0 - band_t
    bar_w = 0.17
    bars = [affinity.rotate(box(-bar_w / 2, 0.0, bar_w / 2, r_i + 0.03),
                            a - 90, origin=(0, 0))
            for a in (90, 210, 330)]
    return [_ring(_circle(1.0), band_t), *bars]


def toyota():
    """Three overlapping elliptical rings forming the stylised T.

    The inner T is a separate island from the outer ring, exactly as in the
    real mark.  The gap at the bottom is opened up slightly from the original
    proportions so a 0.4 mm nozzle still resolves it as a gap.
    """
    a, b = 1.0, 0.704
    return [
        _ring(_ellipse(0.0, 0.0, a, b), 0.100),             # outer
        _ring(_ellipse(0.0, 0.230, 0.74, 0.190), 0.088),    # crossbar
        _ring(_ellipse(0.0, -0.035, 0.255, 0.475), 0.088),  # stem
    ]


LOGOS = {
    "honda": honda,
    "bmw": bmw,
    "mercedes": mercedes,
    "toyota": toyota,
}


def load(name, width_mm):
    """The mark's strokes, scaled so its overall width is `width_mm`."""
    strokes = [_dedupe(s) for s in LOGOS[name]()]
    bounds = np.array([s.bounds for s in strokes])
    k = width_mm / (bounds[:, 2].max() - bounds[:, 0].min())
    return [affinity.scale(s, k, k, origin=(0, 0)) for s in strokes]


def merged(strokes):
    """The strokes welded into one 2D shape -- for measurement, not extrusion."""
    return unary_union(list(strokes))


def parts(shape):
    return list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]


def max_radius(strokes):
    return max(np.hypot(*np.array(s.exterior.coords).T).max() for s in strokes)
