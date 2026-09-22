"""Looks: a background pattern for the face, and a palette of four colours.

The face of a card or fob is one thin coloured layer -- FACE mm deep in
cards.py -- and everything visible on it is an inlay in that layer: the body
colour, a pattern, the lettering.  A look is the pattern the face carries,
the layout the front is set in, and the four colours a multi-material printer
puts in it:

    body       the slab, and the face wherever nothing else is
    pattern    the background decoration
    primary    name, phone, logo, the contactless arcs, the QR code
    secondary  company line, rule, border, the tap wording

Patterns are built here as shapely geometry -- strokes of a fixed width,
which is the "will it print" number -- and clipped by cards.build() to the
face, less a halo around the lettering so it stays readable.  Each is laid
out as read, centred on the origin, x across and y up, in millimetres.
"""
import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

STROKE = 1.1        # pattern line width: two nozzle widths and a bit, prints as a clean inlay
MIN_PIECE = 1.2     # mm^2; anything smaller after clipping is a sliver, drop it


def strokes(lines, width=STROKE):
    return [ln.buffer(width / 2.0, cap_style=1, join_style=1, quad_segs=6) for ln in lines]


def corner(w, h, sx, sy):
    """(x, y) of a corner of the face: sx, sy in {-1, +1}."""
    return sx * w / 2.0, sy * h / 2.0


# ---------------------------------------------------------------------------
# the patterns
# ---------------------------------------------------------------------------
def cube(cx, cy, r, inner=0.62):
    """An isometric cube in outline -- a hexagon with a Y in it -- and a
    smaller one nested inside, the motif on the reference card."""
    lines = []
    for k in (r, r * inner):
        ang = np.radians(np.arange(7) * 60 + 30)
        ring = [(cx + k * np.cos(a), cy + k * np.sin(a)) for a in ang]
        lines.append(LineString(ring))
        for a in np.radians((90, 210, 330)):
            lines.append(LineString([(cx, cy), (cx + k * np.cos(a), cy + k * np.sin(a))]))
    return lines


def cubes(w, h):
    a = cube(-w / 2.0 + 0.11 * w, h / 2.0 + 0.03 * h, 0.50 * h)
    b = cube(w / 2.0 - 0.09 * w, -h / 2.0 - 0.07 * h, 0.56 * h)
    return strokes(a + b, STROKE * 1.15)


def stripes(w, h):
    """Diagonal hatching in two opposite corners."""
    d = w / 2.0 + h / 2.0
    reach = 0.72 * h
    lines = []
    for c in np.arange(-d, -d + reach, 4.2):          # bottom right: y - x = c
        lines.append(LineString([(-w, -w + c), (w, w + c)]))
    for c in np.arange(d, d - reach, -4.2):           # top left
        lines.append(LineString([(-w, -w + c), (w, w + c)]))
    return strokes(lines, STROKE * 0.9)


def grid(w, h, pitch=6.0):
    """Graph paper across the whole face."""
    lines = [LineString([(x, -h), (x, h)]) for x in np.arange(0, w / 2.0 + pitch, pitch)]
    lines += [LineString([(-x, -h), (-x, h)]) for x in np.arange(pitch, w / 2.0 + pitch, pitch)]
    lines += [LineString([(-w, y), (w, y)]) for y in np.arange(0, h / 2.0 + pitch, pitch)]
    lines += [LineString([(-w, -y), (w, -y)]) for y in np.arange(pitch, h / 2.0 + pitch, pitch)]
    return strokes(lines, STROKE * 0.8)


def hexes(w, h, cell=3.4):
    """Honeycomb in two opposite corners."""
    zones = [Point(*corner(w, h, 1, -1)).buffer(0.85 * h, quad_segs=16),
             Point(*corner(w, h, -1, 1)).buffer(0.55 * h, quad_segs=16)]
    dx, dy = np.sqrt(3) * cell, 1.5 * cell
    lines = []
    for j, y in enumerate(np.arange(-h, h + dy, dy)):
        for x in np.arange(-w - dx, w + dx, dx):
            x = x + (dx / 2.0 if j % 2 else 0.0)
            c = Point(x, y)
            if not any(z.intersects(c.buffer(cell)) for z in zones):
                continue
            ang = np.radians(np.arange(7) * 60 + 30)
            lines.append(LineString([(x + cell * np.cos(a), y + cell * np.sin(a)) for a in ang]))
    return strokes(lines, STROKE * 0.8)


def rings(w, h, pitch=5.5):
    """Concentric arcs out of the bottom-left corner, and a few out of the
    top-right one."""
    out = []
    for (sx, sy), reach in (((-1, -1), 1.05 * h), ((1, 1), 0.5 * h)):
        cx, cy = corner(w, h, sx, sy)
        for r in np.arange(pitch, reach, pitch):
            out.append(Point(cx, cy).buffer(r + STROKE / 2.0, quad_segs=24)
                       .difference(Point(cx, cy).buffer(r - STROKE / 2.0, quad_segs=24)))
    return out


def dots(w, h, pitch=4.4, r=0.85):
    """A dot grid in two opposite corners."""
    zones = [Point(*corner(w, h, 1, -1)).buffer(0.8 * h, quad_segs=16),
             Point(*corner(w, h, -1, 1)).buffer(0.5 * h, quad_segs=16)]
    out = []
    for y in np.arange(-h, h, pitch):
        for x in np.arange(-w, w, pitch):
            p = Point(x, y)
            if any(z.contains(p) for z in zones):
                out.append(p.buffer(r, quad_segs=8))
    return out


def disc(w, h):
    """One big solid circle out of the top-right corner, running off both
    edges -- the shape a lot of printed cards use to carry a second colour."""
    return [Point(w / 2.0 - 0.06 * w, h / 2.0 + 0.04 * h).buffer(0.62 * h, quad_segs=48)]


def hexband(w, h, cell=3.0, rows=2, fill=0.88):
    """Solid hexagons along the bottom edge, the upper row shorter than the
    lower one, so the band steps down to the right.

    `fill` is how much of its cell each hexagon takes.  It has to be under 1:
    hexagons packed edge to edge union into one polygon whose boundary touches
    itself, and extruding that is not a closed solid.  The gap is what the
    printed version wants anyway -- and at 12% of 3 mm it is wider than a
    nozzle, so it survives the slicer.
    """
    dx, dy = np.sqrt(3) * cell, 1.5 * cell
    r = cell * fill
    out = []
    for j in range(rows):
        y = -h / 2.0 + cell * 1.05 + j * dy
        reach = (0.66 - 0.28 * j) * w
        x = -w / 2.0 + cell
        while x < -w / 2.0 + reach:
            ang = np.radians(np.arange(6) * 60 + 30)
            out.append(Polygon([(x + r * np.cos(a), y + r * np.sin(a)) for a in ang]))
            x += dx
    return out


def badge(w, h):
    """The disc and the band together: what the `corporate` layout is drawn
    to sit on."""
    return disc(w, h) + hexband(w, h)


PATTERNS = {
    "plain": None,
    "cubes": cubes,
    "stripes": stripes,
    "grid": grid,
    "hexes": hexes,
    "rings": rings,
    "dots": dots,
    "disc": disc,
    "hexband": hexband,
    "badge": badge,
}

TITLES = {
    "plain": "Plain -- no pattern",
    "cubes": "Cubes -- isometric outlines in two corners",
    "stripes": "Stripes -- diagonal hatching in two corners",
    "grid": "Grid -- graph paper across the face",
    "hexes": "Hexes -- honeycomb in two corners",
    "rings": "Rings -- arcs out of two corners",
    "dots": "Dots -- a dot grid in two corners",
    "disc": "Disc -- one big circle off the top-right corner",
    "hexband": "Hex band -- solid hexagons along the bottom",
    "badge": "Badge -- the disc and the hex band together",
}


def pattern(name, w, h, clip, halo=None):
    """The pattern `name` fitted to a face: clipped to `clip` (the face inside
    its chamfer, or inside the border), less `halo` (the lettering, grown),
    as a list of polygons ready to extrude, each handed to the boolean
    engine separately."""
    fn = PATTERNS.get(name or "plain")
    if fn is None:
        return []
    merged = unary_union([p.buffer(0) for p in fn(w, h)]).intersection(clip)
    if halo is not None and not halo.is_empty:
        merged = merged.difference(halo)
    parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    out = []
    for p in parts:
        if p.geom_type != "Polygon" or p.area < MIN_PIECE:
            continue
        # A clipped end can leave a wisp thinner than the stroke.  Measured on
        # the stroke patterns only: a solid shape like the disc is far wider
        # than STROKE everywhere, so the test would never fire on it, but a
        # crescent of one cut by a halo can come out narrow and is worth
        # dropping for the same reason.
        if 2.0 * p.area / p.length < STROKE * 0.4:
            continue
        out.append(p.simplify(0.005))
    return out


# ---------------------------------------------------------------------------
# palettes: body, pattern, primary, secondary
# ---------------------------------------------------------------------------
PRESETS = {
    "printlab": dict(title="Print Lab -- black, white lettering, cubes",
                     pattern="cubes", layout="centred",
                     colours=("#141414", "#2e2e2e", "#f2f2f2", "#9a9a9a")),
    "student":  dict(title="Student -- dark card, name top left, address bottom right",
                     pattern="plain", layout="student",
                     colours=("#1b2430", "#2a3644", "#f4f6f8", "#9fb0c0")),
    "corporate": dict(title="Corporate -- navy, big disc, hexagons along the bottom",
                      pattern="badge", layout="corporate",
                      colours=("#141d3a", "#22305c", "#ffffff", "#c8cede")),
    "citrus":   dict(title="Citrus -- burnt orange, white lettering, hex band",
                     pattern="badge", layout="corporate",
                     colours=("#c4561f", "#a54314", "#ffffff", "#f6cdb6")),
    "slate":    dict(title="Slate -- blue-grey, gold accent, stripes",
                     pattern="stripes", layout="centred", colours=("#2b3a4a", "#3d5063", "#ffffff", "#c9a227")),
    "paper":    dict(title="Paper -- ivory, ink, coral, grid",
                     pattern="grid", layout="centred", colours=("#f2efe6", "#d9d3c4", "#1f1f1f", "#c8412b")),
    "navy":     dict(title="Navy -- navy and gold, rings",
                     pattern="rings", layout="centred", colours=("#1f2a44", "#2c3a5c", "#e8c15a", "#cfd3d6")),
    "forest":   dict(title="Forest -- green, cream, hexes",
                     pattern="hexes", layout="centred", colours=("#1d3b2a", "#2b5038", "#f4efe2", "#d9a441")),
    "ember":    dict(title="Ember -- charcoal, orange, dots",
                     pattern="dots", layout="centred", colours=("#1a1a1a", "#332a2a", "#ff6b35", "#d0d0d0")),
    "plain":    dict(title="Plain -- grey body, gold lettering, no pattern",
                     pattern="plain", layout="centred", colours=("#cfd3d6", "#cfd3d6", "#d9a441", "#d9a441")),
    "wordmark": dict(title="Wordmark -- slate grey, the company in black serif capitals",
                     pattern="plain", layout="wordmark", both_sides=True,
                     colours=("#5b5c5e", "#5b5c5e", "#181818", "#2e2f31")),
}
DEFAULT = "printlab"


def rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def nearest_slot(fill, colours):
    """Which of the four colours an SVG fill is closest to, 0..3; None for
    no fill at all (the shape then goes to primary, the caller decides)."""
    if fill is None:
        return None
    f = np.array(rgb(fill), float)
    d = [np.linalg.norm(f - np.array(rgb(c), float)) for c in colours]
    return int(np.argmin(d))
