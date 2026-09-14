"""Realtor NFC business cards and keyring fobs, built from three fields.

Two bodies, both flat and prismatic:

  card - CR80 credit-card size, 85.6 x 54 mm, the one that lives in a wallet.
  fob  - a smaller keyring tag with a split-ring hole, the open-house handout.

The front carries the name, company and phone raised off the face, so a single
filament change prints the lettering in a second colour.  The back carries a
pocket for an NFC tag and the four-arc contactless mark, raised the same way,
telling whoever is holding it where to put their phone.

Nothing here writes the tag -- that is a phone job (NFC Tools and friends).
The print holds the tag and aims the tapper at it.

Every dimension below is a keyword argument of build(); src/gen_cards.py is the
command line over it and src/app.py the browser UI over that.
"""
from pathlib import Path

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, box
from shapely.ops import unary_union

import trace_svg
import trace_text

QUAD = 32                    # arc resolution, as in logos.py

# Raised lettering narrower than this smears on a 0.4 mm nozzle unless the
# slicer's thin-wall detection is on.  build() measures every line and reports
# what it got rather than refusing: a 0.25 mm nozzle holds a good deal less,
# and the valve caps in this repo print happily down to 0.55 mm.
MIN_STROKE = 0.8

# Fonts.  Any TTF works; these are the ones likely to be on the machine
# already, best first.  A heavy sans is what you want -- the strokes have to
# survive as 0.6 mm-tall bars of plastic.
FONT_SEARCH = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

# How far the lettering and the mark stand off the faces.  0.6 mm is enough to
# read and to take a colour change; 1.2 mm is enough to *feel*, which is the
# point of a thing that lives in a pocket.  The slicer sees it as a few more
# layers of the accent colour before the body starts, nothing else changes.
RISE = 1.2

# A 45-degree break on the outer edges of both faces.  A card this thick with
# a square edge feels like a coaster; 0.6 mm takes the corner off without
# eating into the border.  Set to 0 for a square edge.
CHAMFER = 0.6

# Optional raised QR code on the back, pointing at the same link as the tag.
# Modules are merged into row-runs before extruding, so each raised shape is
# as fat as the code allows.  Anything under QR_MIN_MODULE has no nozzle we
# would name that could print it -- use a shorter link instead.
QR_QUIET = 2               # modules of clear body round the code; spec says 4, 2 scans fine off a matte print
QR_MIN_MODULE = 0.5

# Nozzles people actually own, largest first.  A raised feature prints clean
# when two extrusion lines fit across it, so the nozzle a feature needs is the
# biggest one no more than half its width.
NOZZLES = (0.6, 0.5, 0.4, 0.3, 0.25, 0.2)

# The NFC tag the pocket is cut for.  Default is a rectangular NTAG213
# sticker; measure yours, the sizes vary a lot between sellers.
TAG = dict(w=35.0, h=22.0, thick=0.5, clearance=0.4, corner=1.5)

CARD = dict(
    label="card",
    w=85.6, h=54.0, corner=3.18,    # CR80: the outline of a credit card
    thick=2.2, split_thick=2.6,
    margin=5.0, grow=False,
    hole=None,
    border=0.9, border_inset=3.0,
    rows=[("name", 7.2), ("company", 4.4), ("rule", 0.9), ("phone", 5.4)],
    gaps=[3.0, 3.4, 3.4],
    symbol=18.0, tap_cap=3.4,
)

FOB = dict(
    label="fob",
    w=62.0, h=34.0, corner=4.0,
    thick=2.8, split_thick=3.2,
    margin=3.6, grow=True,          # widened and deepened to fit the tag pocket
    hole=dict(d=4.6, wall=2.2),     # split-ring hole, centred wall + d/2 from the edge
    border=0.0, border_inset=0.0,
    rows=[("name", 5.6), ("company", 3.4), ("rule", 0.8), ("phone", 4.4)],
    gaps=[2.2, 2.6, 2.6],
    symbol=13.0, tap_cap=2.6,
)

BODIES = {"card": CARD, "fob": FOB}

# Register pins on the glue joint of a split body: enough to stop the two
# halves sliding while the glue grabs, small enough to print as a clean stub.
PIN = dict(d=2.4, height=0.6, clearance=0.15, inset=6.0)


# ---------------------------------------------------------------------------
# 2-D primitives
# ---------------------------------------------------------------------------
def rounded_rect(w, h, r, cx=0.0, cy=0.0):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    inner = box(cx - w / 2.0 + r, cy - h / 2.0 + r, cx + w / 2.0 - r, cy + h / 2.0 - r)
    return inner.buffer(r, quad_segs=QUAD, join_style=1) if r else inner


def frame(w, h, r, thickness):
    """A uniform-width outline of a rounded rectangle."""
    outer = rounded_rect(w, h, r)
    return outer.difference(outer.buffer(-thickness))


def extent(polys):
    b = np.array([p.bounds for p in polys])
    return b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()


def stroke_width(poly):
    """Mean stroke width of an elongated shape: 2 * area / perimeter.

    For a bar w x L this is w to within w/L, and for a ring it is the ring
    thickness -- which is the "will it print" question.  It reads low on
    letterforms with counters, whose perimeter runs well ahead of their area,
    so treat the number as a floor rather than a measurement.
    """
    return 2.0 * poly.area / poly.length if poly.length else 0.0


def narrowest(polys):
    return min((stroke_width(p) for p in polys), default=0.0)


# ---------------------------------------------------------------------------
# lettering
# ---------------------------------------------------------------------------
_CAP = {}


def default_font():
    for path in FONT_SEARCH:
        if Path(path).exists():
            return path
    raise SystemExit("no font in the usual places -- pass --font /path/to/Font.ttf")


def cap_per_em(font):
    """Height of a capital H, in em, so that a cap height in millimetres means
    the same thing whatever font is handed in."""
    if font not in _CAP:
        _CAP[font] = max(s.bounds[3] for s in trace_text.trace("H", font))
    return _CAP[font]


def text_polys(text, font, cap_mm, max_w=None, tracking=0.0):
    """One line of lettering, centred on the origin, `cap_mm` tall capitals.

    Returns (polygons, width, cap): `cap` is what the line ended up at, which
    is less than asked for when it had to shrink to fit `max_w`.
    """
    shapes = trace_text.trace(text, font, tracking)
    if not shapes:
        return [], 0.0, 0.0
    k = cap_mm / cap_per_em(font)
    x0, _, x1, _ = extent(shapes)
    width = (x1 - x0) * k
    if max_w and width > max_w:
        k *= max_w / width
        width = max_w
    shapes = [affinity.scale(s, k, k, origin=(0, 0)) for s in shapes]
    cap = cap_per_em(font) * k
    x0, _, x1, _ = extent(shapes)
    # Centred on the capitals rather than on the ink, so a line with descenders
    # still sits on the same optical centre as one without.
    return [affinity.translate(s, -(x0 + x1) / 2.0, -cap / 2.0) for s in shapes], width, cap


def text_block(text, font, cap_mm, max_w, tracking=0.0, leading=1.45):
    """Several lines of lettering, split on newlines or '|', centred as a block.

    Returns (polygons, width, height, cap).  All the lines are set at the cap
    height of the one that had to shrink most, so a two-line block reads as one
    thing rather than as two sizes -- which is the point of splitting a long
    brokerage name over two lines instead of letting it shrink to a smear.
    """
    lines = [ln.strip() for ln in text.replace("|", "\n").split("\n") if ln.strip()]
    rows = [text_polys(ln, font, cap_mm, max_w=max_w, tracking=tracking) for ln in lines]
    rows = [r for r in rows if r[0]]
    if not rows:
        return [], 0.0, 0.0, 0.0
    cap = min(r[2] for r in rows)
    if len(rows) > 1:                        # re-set the short lines to match
        rows = [text_polys(ln, font, cap, max_w=max_w, tracking=tracking)
                for ln in lines if ln]
    step = cap * leading
    height = cap + step * (len(rows) - 1)
    out = []
    for i, (polys, _, _) in enumerate(rows):
        y = height / 2.0 - cap / 2.0 - i * step
        out += [affinity.translate(p, 0.0, y) for p in polys]
    return out, max(r[1] for r in rows), height, cap


# ---------------------------------------------------------------------------
# the contactless mark
# ---------------------------------------------------------------------------
def contactless(height, arcs=4, span=52.0, width=0.13):
    """The four-arc "tap here" mark, `height` tall, arcs opening to the right.

    Built from primitives rather than traced, for the same reason the round car
    emblems in logos.py are: the symmetry is exact and the stroke width is a
    number you can turn up until it prints.  The mark is about 1.8 times taller
    than it is wide, which is the shape everyone reads as "contactless"; the
    NFC Forum N-Mark and the EMVCo indicator are registered marks and these
    plain arcs are neither.
    """
    t = np.radians(np.linspace(-span, span, 64))
    strokes = [LineString(np.column_stack([r * np.cos(t), r * np.sin(t)]))
               .buffer(width / 2.0, cap_style=1, quad_segs=QUAD)
               for r in np.linspace(0.34, 1.0, arcs)]
    x0, y0, x1, y1 = extent(strokes)
    k = height / (y1 - y0)
    strokes = [affinity.scale(s, k, k, origin=(0, 0)) for s in strokes]
    x0, y0, x1, y1 = extent(strokes)
    return [affinity.translate(s, -(x0 + x1) / 2.0, -(y0 + y1) / 2.0) for s in strokes]


# ---------------------------------------------------------------------------
# what needs which nozzle
# ---------------------------------------------------------------------------
def nozzle_for(feature):
    """The largest common nozzle that prints a raised feature `feature` mm wide
    cleanly, i.e. with two lines across it; None if none of them would."""
    return next((n for n in NOZZLES if 2 * n <= feature + 1e-9), None)


# ---------------------------------------------------------------------------
# QR code and logo
# ---------------------------------------------------------------------------
def qr_matrix(text):
    """Rows of booleans for `text`, at the lowest error correction: a raised
    print has all the contrast in the world, and every level up costs modules."""
    import segno
    return [list(r) for r in segno.make(text, error="l", micro=False).matrix]


def qr_polys(rows, module):
    """The dark modules of a QR code as raised shapes, centred on the origin.

    Consecutive dark modules in a row become one rectangle, and every rectangle
    is grown by a hair so that neighbours in adjacent rows overlap rather than
    merely touch -- two boxes that share only an edge or a corner make an
    unwelded seam, and the boolean engine wants volume in common.
    """
    n = len(rows)
    half = n * module / 2.0
    eps = 0.005
    out = []
    for r, row in enumerate(rows):
        c = 0
        while c < n:
            if not row[c]:
                c += 1
                continue
            c0 = c
            while c < n and row[c]:
                c += 1
            out.append(box(c0 * module - half - eps, half - (r + 1) * module - eps,
                           c * module - half + eps, half - r * module + eps))
    return out


def logo_polys(svg, height, max_w):
    """A logo's filled shapes, scaled to `height` (or narrower than `max_w`,
    whichever bites first) and centred on the origin."""
    polys = trace_svg.shapes(svg)
    x0, y0, x1, y1 = extent(polys)
    k = min(height / (y1 - y0), max_w / (x1 - x0))
    polys = [affinity.scale(p, k, k, origin=(0, 0)) for p in polys]
    x0, y0, x1, y1 = extent(polys)
    polys = [affinity.translate(p, -(x0 + x1) / 2.0, -(y0 + y1) / 2.0) for p in polys]
    return polys, x1 - x0, y1 - y0


def finest(polys):
    """The narrowest thing in a set of shapes, counting the holes: a counter
    narrower than a nozzle fills in just as surely as a stroke narrower than
    one smears."""
    widths = [stroke_width(p) for p in polys]
    widths += [stroke_width(Polygon(r)) for p in polys for r in p.interiors]
    return min(widths) if widths else 0.0


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
def content_box(spec, w, h, mirrored=False):
    """The rectangle a face may use: the body less its margins, and less the
    split-ring hole and the meat around it.

    The front is laid out mirrored, so for it the hole has to be kept clear on
    the other side -- get this wrong and the name runs into the keyring.
    """
    x0, x1 = -w / 2.0 + spec["margin"], w / 2.0 - spec["margin"]
    if spec["hole"]:
        keep = spec["hole"]["d"] + spec["hole"]["wall"] + 1.8
        if mirrored:
            x1 = w / 2.0 - keep
        else:
            x0 = -w / 2.0 + keep
    return x0, x1, -h / 2.0 + spec["margin"], h / 2.0 - spec["margin"]


def stack(rows, gaps, cx, cy):
    """Centre a column of (polygons, height) rows on (cx, cy)."""
    total = sum(h for _, h in rows) + sum(gaps)
    y = cy + total / 2.0
    out = []
    for i, (polys, h) in enumerate(rows):
        out += [affinity.translate(p, cx, y - h / 2.0) for p in polys]
        y -= h + (gaps[i] if i < len(gaps) else 0.0)
    return out


def front_face(spec, w, h, fields, font, logo=None, logo_h=None):
    """Name, company, rule and phone, stacked and centred in the content box;
    with a logo, the logo takes the left of the box and the text the rest.

    Laid out as read; build() mirrors it, because this face ends up pointing
    at the build plate.
    """
    x0, x1, y0, y1 = content_box(spec, w, h, mirrored=True)
    inner_w, inner_h = x1 - x0, y1 - y0
    polys, measured, logo_info = [], {}, None

    if logo:
        want = logo_h or inner_h * 0.62
        shapes, lw, lh = logo_polys(logo, want, inner_w * 0.36)
        polys += [affinity.translate(p, x0 + lw / 2.0, (y0 + y1) / 2.0) for p in shapes]
        detail = finest(shapes)
        logo_info = dict(w=round(float(lw), 1), h=round(float(lh), 1),
                         detail=round(float(detail), 2), nozzle=nozzle_for(detail))
        x0 += lw + 4.0
        inner_w = x1 - x0

    rows, gaps = [], []
    for key, cap in spec["rows"]:
        if key == "rule":
            if not rows:
                continue
            shapes = [box(-inner_w * 0.22, -cap / 2.0, inner_w * 0.22, cap / 2.0)]
        else:
            if not fields.get(key):
                continue
            shapes, _, height, cap = text_block(
                fields[key], font, cap, inner_w,
                tracking=0.0 if key == "name" else 0.02)
            if not shapes:
                continue
            measured[key] = dict(cap=round(cap, 2), stroke=round(narrowest(shapes), 2),
                                 lines=fields[key].count("|") + fields[key].count("\n") + 1)
            cap = height
        if rows:
            gaps.append(spec["gaps"][min(len(rows) - 1, len(spec["gaps"]) - 1)])
        rows.append((shapes, cap))

    polys += stack(rows, gaps, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
    if spec["border"]:
        inset = spec["border_inset"]
        polys.append(frame(w - 2 * inset, h - 2 * inset,
                           max(spec["corner"] - inset, 0.8), spec["border"]))
    return polys, measured, logo_info


def mark_block(spec, font, tap_text, zone_w, zone_h):
    """The contactless arcs with the tap wording under them, fitted to a zone.

    The arcs give way first: if the zone is too short for the arcs at full
    size *and* a line of text, the arcs shrink until the text fits, down to
    10 mm.  Below that the text goes instead -- it is the arcs that say "tap".
    """
    sym_h = min(spec["symbol"], zone_h)
    tap, tap_h, tap_cap = [], 0.0, 0.0
    if tap_text:
        tap, _, tap_h, tap_cap = text_block(tap_text, font, spec["tap_cap"], zone_w,
                                            tracking=0.06)
        if tap:
            room = zone_h - 1.8 - tap_h
            if room >= 10.0:
                sym_h = min(sym_h, room)
            if tap_cap < 2.2 or room < 10.0:
                tap, tap_h = [], 0.0
    marks = contactless(sym_h)
    mx0, _, mx1, _ = extent(marks)
    block_h = sym_h + (1.8 + tap_h if tap else 0.0)
    top = block_h / 2.0
    out = [affinity.translate(p, 0.0, top - sym_h / 2.0) for p in marks]
    out += [affinity.translate(p, 0.0, top - sym_h - 1.8 - tap_h / 2.0) for p in tap]
    return out, max(mx1 - mx0, 0.0), block_h, len(tap), len(marks)


def back_face(spec, w, h, pocket_w, pocket_h, tap_text, font, qr=None):
    """The tag pocket, the contactless mark, and if there is a link the QR
    code for it.

    Without a code the mark sits beside the pocket when there is room and
    under it when there is not.  With one, the code takes the right of the
    face and the pocket and mark share the left, pocket on top.

    Laid out as seen from the back, which is also how it is built -- this face
    ends up pointing +Z.
    """
    x0, x1, y0, y1 = content_box(spec, w, h)
    inner_w, inner_h = x1 - x0, y1 - y0
    gap = 3.0
    qr_info = None

    if qr:
        n = len(qr)
        zone_x0 = x0 + pocket_w + gap
        zone_w = x1 - zone_x0
        module = min(zone_w, inner_h) / (n + 2 * QR_QUIET)
        if module < QR_MIN_MODULE:
            raise ValueError(
                f"a {n}-module code in the {zone_w:.0f} x {inner_h:.0f} mm the "
                f"{spec['label']} has spare comes out at {module:.2f} mm a module, which "
                f"nothing prints -- use a shorter link, or the fob, which grows to fit")
        size = (n + 2 * QR_QUIET) * module
        code = [affinity.translate(p, zone_x0 + zone_w / 2.0, (y0 + y1) / 2.0)
                for p in qr_polys(qr, module)]
        qr_info = dict(modules=n, module=round(module, 2), size=round(size, 1),
                       nozzle=nozzle_for(module))
        pocket_c = (x0 + pocket_w / 2.0, y1 - pocket_h / 2.0)
        zone = (pocket_w, inner_h - pocket_h - gap)
        block_c = (x0 + pocket_w / 2.0, y0 + zone[1] / 2.0)
        if zone[1] < 10.0:
            raise ValueError(f"no room under the pocket for the mark on the {spec['label']}")
    else:
        code = []
        marks_probe = contactless(spec["symbol"])
        mx0, _, mx1, _ = extent(marks_probe)
        sym_w = mx1 - mx0
        beside = inner_w - pocket_w - gap
        if beside >= sym_w and pocket_h <= inner_h:
            zone = (beside, inner_h)
            pocket_c = (x0 + pocket_w / 2.0, (y0 + y1) / 2.0)
            block_c = (x1 - beside / 2.0, (y0 + y1) / 2.0)
        elif pocket_w <= inner_w and pocket_h + gap + spec["symbol"] <= inner_h:
            zone = (inner_w, inner_h - pocket_h - gap)
            pocket_c = ((x0 + x1) / 2.0, y1 - pocket_h / 2.0)
            block_c = ((x0 + x1) / 2.0, y0 + zone[1] / 2.0)
        else:
            raise ValueError(
                f"a {pocket_w:.1f} x {pocket_h:.1f} mm pocket and a {sym_w:.0f} x "
                f"{spec['symbol']:.0f} mm mark do not both fit in the {inner_w:.1f} x "
                f"{inner_h:.1f} mm back of the {spec['label']} -- use a smaller tag, "
                f"or the fob, which grows to fit")

    block, _, _, n_tap, n_arcs = mark_block(spec, font, tap_text, *zone)
    marks = [affinity.translate(p, *block_c) for p in block]
    return (rounded_rect(pocket_w, pocket_h, TAG["corner"], *pocket_c),
            marks, code, n_tap, n_arcs, qr_info)


def register_pins(outline, blocked, w, h):
    """Pin positions near the corners that clear the tag cavity and the hole.

    Three of them, never four: three corners of a rectangle are an L, and an L
    does not map onto itself under any flip or half-turn, so the halves only go
    together one way round.  Four pins would let you glue the back on upside
    down and find out afterwards.

    Returns whatever survives, which may be nothing -- a fob whose cavity fills
    it wall to wall has no room for pins, and gluing it flat is no worse.
    """
    room = outline.buffer(-(PIN["d"] / 2.0 + 1.2))
    keep_out = blocked.buffer(1.2)
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = (sx * (w / 2.0 - PIN["inset"]), sy * (h / 2.0 - PIN["inset"]))
            disc = rounded_rect(PIN["d"], PIN["d"], PIN["d"] / 2.0, *c)
            if room.contains(disc) and not disc.intersects(keep_out):
                out.append(c)
    return out[:3]


# ---------------------------------------------------------------------------
# mesh
# ---------------------------------------------------------------------------
def boolean(op, meshes):
    return getattr(trimesh.boolean, op)(meshes, engine="manifold")


def prisms(polys, z0, thickness):
    """One solid per polygon; the caller hands them all to a single boolean."""
    out = []
    for i, poly in enumerate(polys):
        mesh = trimesh.creation.extrude_polygon(poly.simplify(0), thickness)
        if not mesh.is_watertight:
            raise ValueError(f"shape {i} did not extrude to a closed solid")
        mesh.apply_translation((0.0, 0.0, z0))
        out.append(mesh)
    return out


def union(meshes):
    return meshes[0] if len(meshes) == 1 else boolean("union", meshes)


def loft(lower, z0, upper, z1):
    """Watertight solid between two rings with the same vertex count and order.

    rounded_rect() and its inset are built the same way, so an outline and the
    outline `c` mm inside it correspond vertex for vertex -- which is all a
    chamfer is.
    """
    a = np.array(lower.exterior.coords)[:-1]
    b = np.array(upper.exterior.coords)[:-1]
    if len(a) != len(b):
        raise ValueError("loft wants rings with the same vertex count")
    n = len(a)
    verts = np.vstack([np.column_stack([a, np.full(n, z0)]),
                       np.column_stack([b, np.full(n, z1)]),
                       [[0.0, 0.0, z0], [0.0, 0.0, z1]]])
    i = np.arange(n)
    j = (i + 1) % n
    faces = np.vstack([np.column_stack([i, j, n + j]), np.column_stack([i, n + j, n + i]),
                       np.column_stack([np.full(n, 2 * n), j, i]),
                       np.column_stack([np.full(n, 2 * n + 1), n + i, n + j])])
    mesh = trimesh.Trimesh(verts, faces, process=False)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def slab(w, h, r, z0, thick, chamfer):
    """The body: a rounded-rectangle prism with its two outer edges broken."""
    outer = rounded_rect(w, h, r)
    c = min(chamfer, r - 0.2, thick / 2.0 - 0.2)
    if c <= 0.05:
        return prisms([outer], z0, thick)[0]
    inner = rounded_rect(w - 2 * c, h - 2 * c, r - c)
    return boolean("union", [
        loft(inner, z0, outer, z0 + c),
        *prisms([outer], z0 + c - 0.01, thick - 2 * c + 0.02),
        loft(outer, z0 + thick - c, inner, z0 + thick),
    ])


def layout(parts, gap=6.0, row_w=None):
    """[(part, (dx, dy, dz)), ...]: the parts side by side along x on z = 0,
    wrapping into rows no wider than `row_w` -- a batch on one plate."""
    out, x, y, row_h = [], 0.0, 0.0, 0.0
    for part in parts:
        lo, hi = part["mesh"].bounds
        pw, ph = hi[0] - lo[0], hi[1] - lo[1]
        if row_w and x > 0 and x + pw > row_w:
            x, y, row_h = 0.0, y - row_h - gap, 0.0
        out.append((part, (x - lo[0], y - hi[1], -lo[2])))
        x += pw + gap
        row_h = max(row_h, ph)
    return out


def plate(parts, gap=6.0, row_w=None):
    """The parts laid out on one build plate, as a single mesh.

    They are disjoint solids, so this is a concatenation rather than a boolean
    -- every slicer reads it as a multi-part object.
    """
    out = []
    for part, shift in layout(parts, gap, row_w):
        mesh = part["mesh"].copy()
        mesh.apply_translation(shift)
        out.append(mesh)
    return trimesh.util.concatenate(out) if len(out) > 1 else out[0]


def export_3mf(parts, colours=("#cfd3d6", "#d9a441"), gap=6.0, row_w=None):
    """The parts as a 3MF, body and raised features as separate coloured
    components of one object each, so the slicer opens it already knowing the
    lettering is the other filament.

    Written by hand rather than through trimesh's exporter, because what
    matters here is the structure -- one object per part, two components per
    object, two base materials -- and that is easier to get exactly right in
    forty lines of XML than to coax out of a general-purpose scene writer.
    """
    import io
    import zipfile

    def mesh_xml(oid, mesh, pindex, name):
        v = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>'
                    for x, y, z in mesh.vertices)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces)
        return (f'<object id="{oid}" type="model" name="{name}" pid="1" pindex="{pindex}">'
                f'<mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh></object>')

    objects, items, oid = [], [], 2          # id 1 is the material list
    for part, (dx, dy, dz) in layout(parts, gap, row_w):
        label = " ".join(x for x in (part.get("label", ""), part["name"]) if x) or "card"
        ids = []
        for mesh, pindex, what in ((part["body"], 0, "body"), (part["relief"], 1, "raised")):
            if mesh is None:
                continue
            objects.append(mesh_xml(oid, mesh, pindex, f"{label} {what}"))
            ids.append(oid)
            oid += 1
        comps = "".join(f'<component objectid="{i}"/>' for i in ids)
        objects.append(f'<object id="{oid}" type="model" name="{label}">'
                       f'<components>{comps}</components></object>')
        items.append(f'<item objectid="{oid}" '
                     f'transform="1 0 0 0 1 0 0 0 1 {dx:.4f} {dy:.4f} {dz:.4f}"/>')
        oid += 1

    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        '<resources><basematerials id="1">'
        f'<base name="Body" displaycolor="{colours[0]}"/>'
        f'<base name="Raised" displaycolor="{colours[1]}"/>'
        f'</basematerials>{"".join(objects)}</resources>'
        f'<build>{"".join(items)}</build></model>')
    types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '</Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        '</Relationships>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
    return buf.getvalue()


def build(kind, name="", company="", phone="", font=None, tag=None,
          tap_text="TAP HERE", tag_mode="pocket", lid=0.6, border=True, rise=RISE,
          link="", qr=False, logo=None, logo_h=None, chamfer=CHAMFER, label=""):
    """One card or fob as printable parts, plus the numbers worth knowing.

    Returns ([part, ...], info).  Each part is a dict:

      name    "" for a solid body, "front" / "back" for the halves of a split one
      body    the slab, with its cavity, hole and register pins
      relief  the lettering, the mark, the logo and the code, as one separate
              solid (None if there is nothing raised on this part)
      mesh    the two welded into one, for STL

    Keeping body and relief apart is what lets export_3mf() hand the slicer
    two colours; the STL gets the welded mesh and a colour-change height.

    Every part comes out lying down, relief face at z = 0, which is how to
    print it: lettering face-down gets the build-plate finish, and nothing has
    to bridge over the tag cavity.

    tag_mode picks how the tag goes in:

      pocket  an open recess in the back; stick the tag in afterwards.
      embed   the same recess roofed over with `lid` mm; bury the tag by
              pausing the print at the height this reports.
      split   two half-thickness parts to glue together with the tag sandwiched
              between them, register pins on the joint.  The tag ends up on the
              neutral plane with plastic either side, which is the strongest of
              the three and the only one where nothing of the tag shows.

    `logo` is an SVG, as a path or its text, raised on the front beside the
    name.  `link` with `qr=True` raises a QR code for it on the back.  Both
    report the nozzle they need in info["nozzle"].
    """
    spec = {**BODIES[kind]}
    font = font or default_font()
    t = {**TAG, **(tag or {})}
    if not border:
        spec["border"] = 0.0
    split = tag_mode == "split"
    rise = max(0.2, float(rise))
    rows = qr_matrix(link) if (qr and link) else None

    pocket_w = t["w"] + t["clearance"]
    pocket_h = t["h"] + t["clearance"]
    depth = max(t["thick"] + 0.2, 0.6)
    thick = spec["split_thick"] if split else spec["thick"]
    floor = (thick - depth) / 2.0 if split else thick - depth
    if floor < 0.8:
        key = "split_thick" if split else "thick"
        want = depth + (1.6 if split else 0.8)
        raise ValueError(f"a {t['thick']:.1f} mm tag leaves only {floor:.2f} mm of "
                         f"{spec['label']} over it -- raise {key} to {want:.1f} mm or "
                         f"more in cards.py")

    w, h = spec["w"], spec["h"]
    if spec["grow"]:            # the fob is sized by what goes on its back
        x0, x1, _, _ = content_box(spec, w, h)
        sym_w = np.diff(extent(contactless(spec["symbol"]))[0::2])[0]
        if rows:
            code = (len(rows) + 2 * QR_QUIET) * 2 * NOZZLES[2]   # 0.8 mm modules: a 0.4 nozzle
            need_w, need_h = pocket_w + 3.2 + code, max(pocket_h + 3.0 + spec["symbol"], code)
        else:
            need_w, need_h = pocket_w + 3.2 + sym_w, pocket_h
        # 0.2 mm of slack: growing to exactly the width back_face() asks for
        # leaves the fit test to decide on floating-point noise.
        w += max(0.0, need_w - (x1 - x0))
        h = max(h, need_h + 2 * spec["margin"] + 0.2)

    fields = dict(name=name, company=company, phone=phone)
    front, measured, logo_info = front_face(spec, w, h, fields, font, logo, logo_h)
    pocket, marks, code, n_tap, n_arcs, qr_info = back_face(
        spec, w, h, pocket_w, pocket_h, tap_text, font, rows)
    # Both faces are laid out the way you read them.  The back ends up facing
    # +Z and needs nothing done to it; the front faces the build plate, so it
    # is mirrored -- which is exactly what turning the card over does to it.
    front = [affinity.scale(p, -1.0, 1.0, origin=(0, 0)) for p in front]

    z_body, z_back = rise, rise + thick     # the front face and back face of the slab
    outline = rounded_rect(w, h, spec["corner"])

    if split:                   # cavity straddling the joint, half in each part
        z_mid = z_body + thick / 2.0
        cavity, pause_z = (z_mid - depth / 2.0, depth), None
    elif tag_mode == "embed":
        cavity, pause_z = (z_back - lid - depth, depth), z_back - lid
    else:
        cavity, pause_z = (z_back - depth, depth + rise + 1.0), None

    cuts = prisms([pocket], *cavity)
    hole = None
    if spec["hole"]:
        d = spec["hole"]["d"]
        hole = rounded_rect(d, d, d / 2.0, -w / 2.0 + spec["hole"]["wall"] + d / 2.0, 0.0)
        cuts += prisms([hole], -1.0, z_back + rise + 2.0)
    body = boolean("difference", [slab(w, h, spec["corner"], z_body, thick, chamfer), *cuts])

    # The raised work is its own solid, overlapping the slab by a hair so the
    # STL weld has something to bite on and the slicer sees no seam.
    front_relief = union(prisms(front, 0.0, rise + 0.01)) if front else None
    back_polys = marks + code
    back_relief = union(prisms(back_polys, z_back - 0.01, rise + 0.01)) if back_polys else None

    pins = []
    if split:
        blocked = pocket if hole is None else unary_union([pocket, hole])
        pins = register_pins(outline, blocked, w, h)
        parts = halve(body, front_relief, back_relief, z_mid, pins, w, h)
    else:
        reliefs = [m for m in (front_relief, back_relief) if m is not None]
        parts = [dict(name="", body=body, relief=union(reliefs) if reliefs else None)]
    for part in parts:
        part["label"] = label
        part["mesh"] = (part["body"] if part["relief"] is None
                        else boolean("union", [part["body"], part["relief"]]))

    arcs = marks[:n_arcs]
    tap = marks[n_arcs:]
    needs = [x["nozzle"] for x in (qr_info, logo_info) if x]
    info = dict(
        kind=kind, label=label, w=round(w, 2), h=round(h, 2), thick=thick, rise=rise,
        chamfer=round(min(chamfer, spec["corner"] - 0.2, thick / 2.0 - 0.2), 2),
        parts=[p["name"] or kind for p in parts], pins=len(pins),
        part_thick=round(rise + (thick / 2.0 if split else thick), 2),
        assembled=round(2 * rise + thick, 2),
        pocket=[round(pocket_w, 2), round(pocket_h, 2), round(depth, 2)],
        tag_mode=tag_mode, lines=measured, logo=logo_info, qr=qr_info,
        # None here means a feature is too fine for any nozzle we would name.
        nozzle=(None if any(n is None for n in needs) else min(needs)) if needs else None,
        mark_stroke=round(narrowest(arcs), 2),
        tap_stroke=round(narrowest(tap), 2) if tap else None,
        pause_z=None if pause_z is None else round(pause_z, 2),
        volume=round(sum(p["mesh"].volume for p in parts) / 1000.0, 2),
        watertight=all(p["mesh"].is_watertight and p["mesh"].is_winding_consistent
                       for p in parts),
        font=Path(font).name,
    )
    info["total_z"] = round(max(p["mesh"].bounds[1][2] for p in parts), 2)
    # Where the filament changes go.  Both halves of a split body print relief
    # down, so they take one change each and there is no second one.
    info["change_up"] = round(rise, 2)
    info["change_back"] = info["total_z"] + 1.0 if split else round(z_back, 2)
    info["changes"] = [info["change_up"]] if split else [info["change_up"],
                                                         info["change_back"]]
    info["thin"] = sorted(k for k, v in measured.items() if v["stroke"] < MIN_STROKE)
    if info["tap_stroke"] and info["tap_stroke"] < MIN_STROKE:
        info["thin"].append("tap text")
    return parts, info


def halve(body, front_relief, back_relief, z_mid, pins, w, h):
    """Cut the slab at the glue joint and hand the front half the pins.

    The relief needs no cutting: the front lettering lies wholly below the
    joint and the back mark wholly above it, so each simply goes with its half.

    The back half is then turned over about Y, so both parts print relief-down
    with their mating faces up -- pins print as stubs rather than as holes
    needing support, and both halves read the right way up on the plate.  Y
    rather than X because turning it the other way would leave the arcs upside
    down on the build plate; either is the same solid, and either assembles the
    same way, since the pins go back where they started when the half is turned
    over again to glue it.
    """
    span = rounded_rect(w + 10.0, h + 10.0, 0.0)
    lo = prisms([span], -1.0, z_mid + 1.0)
    hi = prisms([span], z_mid, body.bounds[1][2] + 1.0)

    studs = [rounded_rect(PIN["d"], PIN["d"], PIN["d"] / 2.0, *c) for c in pins]
    bores = [rounded_rect(PIN["d"] + 2 * PIN["clearance"], PIN["d"] + 2 * PIN["clearance"],
                          PIN["d"] / 2.0 + PIN["clearance"], *c) for c in pins]

    front = boolean("intersection", [body, *lo])
    if studs:
        front = boolean("union", [front, *prisms(studs, z_mid - 0.3, PIN["height"] + 0.3)])
    back = boolean("intersection", [body, *hi])
    if bores:
        back = boolean("difference",
                       [back, *prisms(bores, z_mid - 0.01, PIN["height"] + 0.16)])

    flip = trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0])
    parts = [dict(name="front", body=front, relief=front_relief),
             dict(name="back", body=back, relief=back_relief)]
    for part in parts:
        solids = [m for m in (part["body"], part["relief"]) if m is not None]
        if part["name"] == "back":
            for m in solids:
                m.apply_transform(flip)
        drop = min(m.bounds[0][2] for m in solids)
        for m in solids:
            m.apply_translation((0.0, 0.0, -drop))
    return parts


# ---------------------------------------------------------------------------
# batches
# ---------------------------------------------------------------------------
def parse_batch(text):
    """One person per line: name, company, phone, link -- separated by tabs
    (which is what pasting from a spreadsheet gives) or commas.  Company and
    link may be left empty; a line starting with # is a comment."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cells = [c.strip() for c in (line.split("\t") if "\t" in line else line.split(","))]
        cells += [""] * (4 - len(cells))
        name, company, phone, link = cells[:4]
        if not name:
            raise ValueError(f"no name on this line: {raw!r}")
        rows.append(dict(name=name, company=company, phone=phone, link=link))
    return rows


def build_batch(rows, kind, **kw):
    """Every row as its own part(s), labelled by name; one list, one plate."""
    parts, infos = [], []
    for row in rows:
        p, info = build(kind, name=row["name"], company=row["company"], phone=row["phone"],
                        link=row["link"] or kw.get("link", ""), label=row["name"],
                        **{k: v for k, v in kw.items() if k != "link"})
        parts += p
        infos.append(info)
    return parts, infos
