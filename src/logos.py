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
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

OUTLINE = Path(__file__).resolve().parent / "logo_outline.json"
WORDMARK = Path(__file__).resolve().parent / "ford_wordmark.json"
FORD_SCRIPT = Path(__file__).resolve().parent / "ford_script.json"
QUAD = 64  # arc resolution


def _circle(r, cx=0.0, cy=0.0):
    return Point(cx, cy).buffer(r, quad_segs=QUAD)


def _stroke(points, width):
    """A mitred polyline of constant width -- the strokes of a letterform."""
    return LineString(points).buffer(width / 2.0, cap_style=2, join_style=2)


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


def audi():
    """Four interlocking rings.

    The rings are drawn heavier than the real mark: at this size correct
    proportions put the stroke at 0.28 mm, which no 0.4 mm nozzle will hold.
    """
    r, t, spacing = 0.5, 0.145, 0.78
    return [_ring(_circle(r, cx=x * spacing, cy=0.0), t)
            for x in (-1.5, -0.5, 0.5, 1.5)]


def volkswagen():
    """V over W inside a ring.

    Both letters are clipped to the ring so nothing pokes out past it, and the
    W sits lower than in the real mark to keep a printable gap under the V.
    """
    disc = _circle(1.0)
    # Both letters run past the outer circle before being clipped back: ending
    # them inside the ring instead leaves a hairline sliver along its inner edge.
    v = _stroke([(-0.80, 0.70), (0.0, 0.20), (0.80, 0.70)], 0.13)
    w = _stroke([(-1.05, 0.02), (-0.50, -0.92), (0.0, -0.10),
                 (0.50, -0.92), (1.05, 0.02)], 0.13)
    return [_ring(disc, 0.09), v.intersection(disc), w.intersection(disc)]


def mitsubishi():
    """Three rhombi at 120 degrees, held off the centre by a small gap."""
    gap, tip, half = 0.07, 1.0, 0.275
    dia = Polygon([(0.0, gap), (-half, (gap + tip) / 2), (0.0, tip), (half, (gap + tip) / 2)])
    return [affinity.rotate(dia, a, origin=(0, 0)) for a in (0, 120, 240)]


def jeep():
    """The seven-slot grille and two round headlights."""
    slot_w, spacing, half_h = 0.115, 0.20, 0.62
    slots = [_stroke([(i * spacing, -half_h + slot_w / 2),
                      (i * spacing, half_h - slot_w / 2)], slot_w)
             for i in range(-3, 4)]
    lamps = [_circle(0.34, cx=x, cy=0.0) for x in (-1.04, 1.04)]
    return [*slots, *lamps]


def chevrolet():
    """The bowtie: a squat cross with the ends of the long bar cut back."""
    return [Polygon([
        (-0.86, 0.19), (-0.32, 0.19), (-0.32, 0.46), (0.32, 0.46),
        (0.32, 0.19), (1.00, 0.19), (0.86, -0.19), (0.32, -0.19),
        (0.32, -0.46), (-0.32, -0.46), (-0.32, -0.19), (-1.00, -0.19),
    ])]


def volvo():
    """The iron mark: a ring with the arrow of Mars at 45 degrees."""
    ring = _ring(_circle(1.0), 0.14)
    shaft = _stroke([(0.58, 0.58), (0.98, 0.98)], 0.19)
    head = Polygon([(1.30, 1.30), (0.738, 1.162), (1.162, 0.738)])
    return [ring, shaft, head]


def ford():
    """FORD in the Blue Oval -- block capitals, not the script.

    The real script needs a 0.38 mm stroke at this size, which is under one
    extrusion, so no nozzle will render it legibly however well it is drawn.
    Capitals at 0.51 mm actually come out.  The letters are cut *through* the
    oval pad (see PADS) rather than standing proud of it, so a filament change
    gives light letters on a coloured oval, the way the badge really looks.
    """
    data = json.loads(WORDMARK.read_text())
    shapes = [Polygon(g["exterior"], g["holes"]).buffer(0) for g in data["shapes"]]
    b = np.array([g.bounds for g in shapes])
    k = WORD_W / (b[:, 2].max() - b[:, 0].min())
    cx = (b[:, 0].min() + b[:, 2].max()) / 2.0
    cy = (b[:, 1].min() + b[:, 3].max()) / 2.0
    return [affinity.scale(affinity.translate(g, -cx, -cy), k, k, origin=(0, 0))
            for g in shapes]


def _ford_oval():
    return _ellipse(0.0, 0.0, 1.0, OVAL_B)


def _ford_script_json():
    d = json.loads(FORD_SCRIPT.read_text())
    pad = Polygon(d["pad"]["exterior"], d["pad"]["holes"])
    cuts = [Polygon(c["exterior"], c["holes"]) for c in d["cuts"]]
    k = 2.0 / (pad.bounds[2] - pad.bounds[0])
    scale = lambda g: affinity.scale(g, k, k, origin=(0, 0))
    return scale(pad), [scale(c) for c in cuts]


def ford_script():
    """The real Ford script and oval rings, traced from the logo.

    This is the genuine artwork, not an interpretation -- and it is why it
    needs a bigger cap than the rest.  The script is a copperplate hand whose
    upstrokes are hairlines: at a 13.1 mm oval the channels measure 0.19 mm
    median, half a nozzle width, and 95% of the lettering falls under 0.40 mm.
    Fattening it does not help, because widening the channels to a printable
    0.45 mm starves the pad *between* the strokes down to 0.09 mm -- you just
    trade one unprintable feature for the other.  See FLAT_OVERRIDES.
    """
    return _ford_script_json()[1]


def _ford_script_pad():
    return _ford_script_json()[0]


OVAL_B = 0.385   # Blue Oval is about 2.6:1
WORD_W = 1.40   # word width in oval half-widths: 70% of the oval

# Marks drawn as a solid pad with the strokes cut out of it, rather than as
# strokes standing proud of the flat top.
PADS = {"ford": _ford_oval, "ford_script": _ford_script_pad}

LOGOS = {
    "honda": honda,
    "bmw": bmw,
    "mercedes": mercedes,
    "toyota": toyota,
    "audi": audi,
    "volkswagen": volkswagen,
    "mitsubishi": mitsubishi,
    "jeep": jeep,
    "chevrolet": chevrolet,
    "volvo": volvo,
    "ford": ford,
    "ford_script": ford_script,
}


def _placed(name, width_mm):
    """Strokes and pad, centred on the origin and scaled to `width_mm` wide.

    Both are normalised against the same bounding box -- which the pad
    dominates when there is one -- so they stay registered to each other.
    """
    raw = []
    for stroke in LOGOS[name]():
        raw.extend(parts(stroke))        # a clip can split a stroke in two
    strokes = [_dedupe(s) for s in raw]
    pad = _dedupe(PADS[name]()) if name in PADS else None

    ref = strokes if pad is None else [pad, *strokes]
    b = np.array([g.bounds for g in ref])
    cx = (b[:, 0].min() + b[:, 2].max()) / 2.0
    cy = (b[:, 1].min() + b[:, 3].max()) / 2.0
    k = width_mm / (b[:, 2].max() - b[:, 0].min())

    def place(g):
        return affinity.scale(affinity.translate(g, -cx, -cy), k, k, origin=(0, 0))

    return [place(s) for s in strokes], (place(pad) if pad is not None else None)


def load(name, width_mm):
    """The mark's strokes, centred on the origin and scaled to `width_mm` wide."""
    return _placed(name, width_mm)[0]


def load_pad(name, width_mm):
    """The solid pad the strokes are cut out of, or None for a raised mark."""
    return _placed(name, width_mm)[1]


def fit_width(name, max_r):
    """The width that makes the mark reach exactly `max_r` from its centre."""
    strokes, pad = _placed(name, 2.0)
    return 2.0 * max_r / max_radius(strokes if pad is None else [pad])


def merged(strokes):
    """The strokes welded into one 2D shape -- for measurement, not extrusion."""
    return unary_union(list(strokes))


def parts(shape):
    return list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]


def max_radius(strokes):
    return max(np.hypot(*np.array(s.exterior.coords).T).max() for s in strokes)
