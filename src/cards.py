"""Realtor NFC business cards and keyring fobs, built from three fields.

Two bodies, both flat and prismatic:

  card - CR80 credit-card size, 85.6 x 54 mm, the one that lives in a wallet.
  fob  - a smaller keyring tag with a split-ring hole, the open-house handout.

The front carries the name, company and phone, the back a pocket for an NFC
tag and the four-arc contactless mark telling whoever is holding it where to
put their phone.  Everything visible is an inlay in one thin face layer, in up
to four colours -- body, a background pattern, primary and secondary lettering
-- so a multi-material printer does all its colour changes in the first few
layers and prints the rest of the part in one.  Lettering can also stand off
the face (`rise`) for a tactile card at the cost of more colour changes.

Nothing here writes the tag -- that is a phone job (NFC Tools and friends).
The print holds the tag and aims the tapper at it.

Every dimension below is a keyword argument of build(); src/gen_cards.py is the
command line over it and src/app.py the browser UI over that.
"""
from pathlib import Path

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.geometry import box as box_2d
from shapely.ops import unary_union

import looks
import trace_svg
import trace_text

QUAD = 32                    # arc resolution, as in logos.py

# Raised lettering narrower than this smears on a 0.4 mm nozzle unless the
# slicer's thin-wall detection is on.  build() measures every line and reports
# what it got rather than refusing: a 0.25 mm nozzle holds a good deal less,
# and the valve caps in this repo print happily down to 0.55 mm.
MIN_STROKE = 0.8

# Fonts.  Any TTF works.  Liberation Sans Bold ships in src/fonts (SIL Open
# Font License, text alongside it) -- next to the code rather than under
# public/, because a hosted function is guaranteed to carry its source and
# not necessarily anything else -- so the generator has the same face on every
# machine and on Vercel, where there are no system fonts at all.  The rest are
# fallbacks.  A heavy sans is what you want: the strokes have to survive as
# 1.2 mm-tall bars of plastic.
FONT_DIR = Path(__file__).resolve().parent / "fonts"

FONT_SEARCH = [
    str(FONT_DIR / "LiberationSans-Bold.ttf"),
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

# The faces offered by name, all SIL Open Font License with their licence text
# alongside them in src/fonts.  A card is mostly its wording and one face does
# for it; a keychain *is* its lettering, so the choice matters much more there
# -- and what a face costs is printability, which the readout reports: the
# fatter the letterform the wider its narrowest stroke and the coarser the
# nozzle it will take.
FONTS = {
    "Liberation Sans Bold": "LiberationSans-Bold.ttf",
    "Erica One":            "EricaOne-Regular.ttf",
    "Boldonse":             "Boldonse-Regular.ttf",
    "Outfit Bold":          "Outfit-Bold.ttf",
    "National Park Bold":   "NationalPark-Bold.ttf",
    "Big Shoulders Bold":   "BigShoulders-Bold.ttf",
    "Tektur":               "Tektur-Medium.ttf",
    "Lora Bold":            "Lora-Bold.ttf",
    "Silkscreen":           "Silkscreen-Regular.ttf",
    "Nothing You Could Do": "NothingYouCouldDo-Regular.ttf",
}

# Where a character the chosen face has not got comes from.  Monochrome, and
# that is the whole point: a colour emoji font stores bitmaps, and a bitmap
# has no outline to extrude.  Noto Emoji at weight 700, whose strokes are the
# fattest of the family and so the likeliest to print.
EMOJI = str(FONT_DIR / "NotoEmoji-Bold.ttf")

# The face: one thin layer, FACE mm deep, that every colour lives in -- the
# body colour where nothing else is, the pattern, the lettering, all flush
# with each other like ink on a printed card.  Printed face down, that is the
# first three layers at 0.2 mm; a multi-material printer does all its colour
# changes there and prints the rest of the part in the body colour with none.
FACE = 0.6

# The four colours, in the order the 3MF's materials and the viewer use them.
SLOTS = ("body", "pattern", "primary", "secondary")
COLOURS = looks.PRESETS[looks.DEFAULT]["colours"]

# How far the lettering and the mark stand off the face, on top of the inlay.
# 0 is flush: a smooth card, every colour in the face layer.  1.2 mm is enough
# to *feel*, at the cost of a colour change every layer the relief runs
# through.  Whatever it is, the lettering roots through the face layer too, so
# the face reads the same either way.
RISE = 0.0

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
    # Name, company, title, then the contact details under a rule: the five
    # things every guide to business cards agrees on, in the order they read.
    # Any of them left empty is simply skipped.
    rows=[("name", 7.2), ("company", 4.4), ("role", 3.6), ("rule", 0.9),
          ("phone", 4.8), ("email", 3.8)],
    gaps=[2.6, 2.2, 3.0, 2.8, 2.0],
    symbol=18.0, tap_cap=3.4,
)

FOB = dict(
    label="fob",
    w=62.0, h=34.0, corner=4.0,
    thick=2.8, split_thick=3.2,
    margin=3.6, grow=True,          # widened and deepened to fit the tag pocket
    hole=dict(d=4.6, wall=2.2),     # split-ring hole, centred wall + d/2 from the edge
    border=0.0, border_inset=0.0,
    rows=[("name", 5.6), ("company", 3.4), ("role", 2.8), ("rule", 0.8),
          ("phone", 4.0), ("email", 2.8)],
    gaps=[1.8, 1.6, 2.2, 2.0, 1.5],
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
    inner = box_2d(cx - w / 2.0 + r, cy - h / 2.0 + r, cx + w / 2.0 - r, cy + h / 2.0 - r)
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
    """The first font in FONT_SEARCH that exists.

    A miss is an ordinary error, not a SystemExit: raised inside a request
    handler, SystemExit takes the whole process down with no traceback, which
    is exactly how the hosted version first failed.
    """
    for path in FONT_SEARCH:
        if Path(path).exists():
            return path
    raise FileNotFoundError("no font found; looked in " + ", ".join(FONT_SEARCH)
                            + " -- pass --font /path/to/Font.ttf")


def font_path(font):
    """A path for whatever was asked for: one of FONTS by name, a path to a TTF
    of your own, or nothing at all, which gets the first face that exists."""
    if not font:
        return default_font()
    if font in FONTS:
        return str(FONT_DIR / FONTS[font])
    if Path(font).exists():
        return str(font)
    raise ValueError(f"no such font: {font} -- pick one of {', '.join(FONTS)}, "
                     f"or give the path to a TTF")


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
    shapes = trace_text.trace(text, font, tracking, fallback=EMOJI)
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


def text_block(text, font, cap_mm, max_w, tracking=0.0, leading=1.45, align="center"):
    """Several lines of lettering, split on newlines or '|', as one block
    centred on the origin.

    Returns (polygons, width, height, cap).  All the lines are set at the cap
    height of the one that had to shrink most, so a two-line block reads as one
    thing rather than as two sizes -- which is the point of splitting a long
    brokerage name over two lines instead of letting it shrink to a smear.

    `align` is how the lines sit within the block -- the block itself is always
    centred on the origin, and place_block() is what moves it somewhere.
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
    width = max(r[1] for r in rows)
    out = []
    for i, (polys, row_w, _) in enumerate(rows):
        y = height / 2.0 - cap / 2.0 - i * step
        slack = (width - row_w) / 2.0
        x = {"center": 0.0, "left": -slack, "right": slack}[align]
        out += [affinity.translate(p, x, y) for p in polys]
    return out, width, height, cap


def place_block(text, font, cap_mm, max_w, x, y, align="left", anchor="top", **kw):
    """A block of lettering anchored at (x, y) rather than centred on the
    origin: `align` puts its left edge, centre or right edge on x, `anchor`
    its top, middle or bottom on y.

    Returns (polygons, width, height, cap) -- the caller wants the height to
    know where the next thing goes.
    """
    polys, w, h, cap = text_block(text, font, cap_mm, max_w, align=align, **kw)
    if not polys:
        return [], 0.0, 0.0, 0.0
    dx = {"left": w / 2.0, "center": 0.0, "right": -w / 2.0}[align]
    dy = {"top": -h / 2.0, "middle": 0.0, "bottom": h / 2.0}[anchor]
    return [affinity.translate(p, x + dx, y + dy) for p in polys], w, h, cap


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


def chevrons(height, n=2, width=0.16, spread=0.58):
    """`n` nested > marks, `height` tall, opening right -- the little "go to"
    arrow that sits in front of an address on a card.

    Built from a polyline rather than set from the font's own ">", for the
    reason the contactless arcs are: the stroke width is then a number you can
    turn up until it prints, rather than whatever the type designer chose.
    """
    marks = [LineString([(i * spread, 1.0), (i * spread + 0.72, 0.0),
                         (i * spread, -1.0)])
             .buffer(width / 2.0, cap_style=2, join_style=1, quad_segs=QUAD)
             for i in range(n)]
    x0, y0, x1, y1 = extent(marks)
    k = height / (y1 - y0)
    marks = [affinity.scale(m, k, k, origin=(0, 0)) for m in marks]
    x0, y0, x1, y1 = extent(marks)
    return [affinity.translate(m, -(x0 + x1) / 2.0, -(y0 + y1) / 2.0) for m in marks]


def logo_box(size, font, label="Logo", thickness=0.9, cx=0.0, cy=0.0):
    """An empty outlined square with a word in it, for a layout that has a
    place for a logo and no logo to put there.

    It is a placeholder in the literal sense: it shows where the artwork goes
    and what size it can be, and you turn it off (or hand over an SVG) before
    printing the real thing.
    """
    outer = rounded_rect(size, size, size * 0.06, cx, cy)
    polys = [outer.difference(outer.buffer(-thickness))]
    if label:
        txt, _, _, _ = text_block(label, font, size * 0.21, size * 0.60)
        polys += [affinity.translate(t, cx, cy) for t in txt]
    return polys


def hexagon(cx, cy, r):
    ang = np.radians(np.arange(6) * 60 + 30)
    return Polygon([(cx + r * np.cos(a), cy + r * np.sin(a)) for a in ang])


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

    Each dark module is grown by a twentieth of itself and the lot is merged in
    2-D, so neighbours -- side by side or corner to corner -- become one shape
    with a real overlap rather than a shared edge or a shared point.  Shared
    edges and points are what break extrusion: a ring that touches itself is
    not a valid polygon, and overlapping them by a hair in 3-D instead leaves
    slivers that collapse into degenerate triangles the moment a slicer merges
    close vertices on import.  A 5% bleed costs the light gaps a tenth of a
    module, which a scanner does not notice on a dark-on-light print.
    """
    n = len(rows)
    half = n * module / 2.0
    bleed = module * 0.05
    squares = [box_2d(c * module - half - bleed, half - (r + 1) * module - bleed,
                   (c + 1) * module - half + bleed, half - r * module + bleed)
               for r, row in enumerate(rows) for c, dark in enumerate(row) if dark]
    merged = unary_union(squares)
    return list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]


def logo_polys(svg, height, max_w, colours=None):
    """A logo's filled shapes, scaled to `height` (or narrower than `max_w`,
    whichever bites first) and centred on the origin.

    Returns (layers, width, height): `layers` maps a slot name to polygons.
    With `colours` -- the four the card will print in -- each fill in the
    file goes to the slot whose colour it is nearest, and shapes in the body
    colour are dropped as background (a card drawn on a black rectangle
    comes out as its lettering on the black body, at the rectangle's size,
    which is what was meant).  Without, or when nothing survives, the whole
    thing is primary.
    """
    groups = trace_svg.shapes(svg, fills=True)
    every = [p for _, polys in groups for p in polys]
    x0, y0, x1, y1 = extent(every)
    k = min(height / (y1 - y0), max_w / (x1 - x0))
    cx, cy = (x0 + x1) / 2.0 * k, (y0 + y1) / 2.0 * k
    fit = lambda p: affinity.translate(affinity.scale(p, k, k, origin=(0, 0)), -cx, -cy)

    layers = {}
    if colours:
        for fill, polys in groups:
            slot = looks.nearest_slot(fill, colours)
            slot = SLOTS[slot] if slot is not None else "primary"
            if slot == "body":
                continue
            layers.setdefault(slot, []).extend(fit(p) for p in polys)
    if not layers:
        layers = {"primary": [fit(p) for p in every]}
    return layers, (x1 - x0) * k, (y1 - y0) * k


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


def fit_logo(logo, height, max_w, colours, font, placeholder, cx, cy):
    """The logo, scaled and centred on (cx, cy) -- or, with nothing to put
    there, the placeholder a layout asked for.

    Returns (layers, width, height, info): `layers` is keyed by colour slot,
    and `info` is None for a placeholder, which is not the designer's artwork
    and has no business reporting the nozzle it needs.
    """
    if logo:
        shapes, lw, lh = logo_polys(logo, height, max_w, colours)
        layers = {slot: [affinity.translate(p, cx, cy) for p in polys]
                  for slot, polys in shapes.items()}
        detail = finest([p for polys in shapes.values() for p in polys])
        return layers, lw, lh, dict(
            w=round(float(lw), 1), h=round(float(lh), 1),
            detail=round(float(detail), 2), nozzle=nozzle_for(detail),
            slots=sorted(shapes, key=SLOTS.index))
    if not placeholder:
        return {}, 0.0, 0.0, None
    size = min(height, max_w)
    polys = ([hexagon(cx, cy, size / 2.0)] if placeholder == "hex"
             else logo_box(size, font, cx=cx, cy=cy))
    return {"primary": polys}, size, size, None


def measure(shapes, cap, text):
    return dict(cap=round(cap, 2), stroke=round(narrowest(shapes), 2),
                lines=text.count("|") + text.count("\n") + 1)


class Face:
    """What a layout builds: polygons filed under the colour they print in and
    the field they came from.

    The colour is what the slicer needs -- it is the 3MF's materials -- and the
    field is what the app needs, so that putting the cursor in the Email box
    can light up the email on the part.  Both are wanted, so both are kept.
    """

    def __init__(self):
        self.groups = {}
        self.measured = {}

    def add(self, slot, element, polys):
        if polys:
            self.groups.setdefault((slot, element), []).extend(polys)

    def note(self, key, shapes, cap, text):
        self.measured[key] = measure(shapes, cap, text)

    @property
    def ink(self):
        return [p for polys in self.groups.values() for p in polys]


def layout_centred(spec, w, h, box, fields, font, logo, logo_h, colours, placeholder):
    """Name, company, title, a rule and the contact details, stacked and
    centred; with a logo, the logo takes the left of the box and the text the
    rest.  The original, and the one that copes best with a fob.

    The stack shrinks to fit when it is taller than the face: six lines on a
    fob would otherwise run off both ends of it.
    """
    x0, x1, y0, y1 = box
    inner_w, inner_h = x1 - x0, y1 - y0
    face = Face()
    logo_info = None

    if logo or placeholder:
        want = logo_h or inner_h * 0.62
        shapes, lw, lh, logo_info = fit_logo(
            logo, want, inner_w * 0.36, colours, font, placeholder,
            x0 + min(want, inner_w * 0.36) / 2.0, (y0 + y1) / 2.0)
        for slot, polys in shapes.items():
            face.add(slot, "logo", polys)
        x0 += lw + 4.0
        inner_w = x1 - x0

    def typeset(scale):
        rows, gaps, keys = [], [], []
        for key, cap in spec["rows"]:
            if key == "rule":
                if not rows:
                    continue
                shapes = [box_2d(-inner_w * 0.22, -cap * scale / 2.0,
                                 inner_w * 0.22, cap * scale / 2.0)]
                height = cap * scale
            else:
                if not fields.get(key):
                    continue
                shapes, _, height, cap = text_block(
                    fields[key], font, cap * scale, inner_w,
                    tracking=0.0 if key == "name" else 0.02)
                if not shapes:
                    continue
            if rows:
                gaps.append(spec["gaps"][min(len(rows) - 1, len(spec["gaps"]) - 1)] * scale)
            rows.append((shapes, height, cap))
            keys.append(key)
        total = sum(r[1] for r in rows) + sum(gaps)
        return rows, gaps, keys, total

    rows, gaps, keys, total = typeset(1.0)
    if total > inner_h and total > 0:
        rows, gaps, keys, total = typeset(inner_h / total)

    placed = stack([(r[0], r[1]) for r in rows], gaps, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
    i = 0
    for (shapes, _, cap), key in zip(rows, keys):
        slot = "primary" if key in ("name", "phone") else "secondary"
        face.add(slot, key, placed[i:i + len(shapes)])
        if key != "rule":
            face.note(key, shapes, cap, fields[key])
        i += len(shapes)
    return face, logo_info


def layout_student(spec, w, h, box, fields, font, logo, logo_h, colours, placeholder):
    """Name big at the top left, a logo square at the top right, two lines of
    who-you-are under the name, and an address along the bottom right behind a
    pair of chevrons.  The layout of a student or staff card."""
    x0, x1, y0, y1 = box
    W, H = x1 - x0, y1 - y0
    face = Face()

    size = logo_h or H * 0.30
    shapes, lw, lh, logo_info = fit_logo(logo, size, min(size, W * 0.26), colours,
                                         font, placeholder, 0.0, 0.0)
    if shapes:
        shift = (x1 - lw / 2.0, y1 - lh / 2.0)
        for slot, polys in shapes.items():
            face.add(slot, "logo", [affinity.translate(p, *shift) for p in polys])
    text_w = (x1 - (lw + H * 0.09 if lw else 0.0)) - x0

    y = y1
    if fields.get("name"):
        polys, _, bh, cap = place_block(fields["name"], font, H * 0.135, text_w,
                                        x0, y, align="left", anchor="top")
        if polys:
            face.add("primary", "name", polys)
            face.note("name", polys, cap, fields["name"])
            y -= bh + H * 0.13

    for key, slot in (("role", "secondary"), ("company", "primary")):
        if not fields.get(key):
            continue
        polys, _, bh, cap = place_block(fields[key], font, H * 0.085, W * 0.78,
                                        x0, y, align="left", anchor="top",
                                        tracking=0.01)
        if polys:
            face.add(slot, key, polys)
            face.note(key, polys, cap, fields[key])
            y -= bh + H * 0.055

    key = "email" if fields.get("email") else "phone"
    if fields.get(key):
        txt, tw, th, cap = text_block(fields[key], font, H * 0.07, W * 0.72, tracking=0.01)
        if txt:
            marks = chevrons(cap)
            mx0, _, mx1, _ = extent(marks)
            mw, gap = mx1 - mx0, cap * 0.55
            left = x1 - (mw + gap + tw)
            mid = y0 + th / 2.0
            face.add("primary", key, [affinity.translate(m, left + mw / 2.0, mid)
                                      for m in marks])
            face.add("secondary", key, [affinity.translate(t, left + mw + gap + tw / 2.0,
                                                           mid) for t in txt])
            face.note(key, txt, cap, fields[key])
    return face, logo_info


def layout_corporate(spec, w, h, box, fields, font, logo, logo_h, colours, placeholder):
    """A mark and the company across the top left, a slogan under it, and the
    person down in the bottom left -- the layout that wants a big shape behind
    it, so pair it with the `badge` pattern."""
    x0, x1, y0, y1 = box
    W, H = x1 - x0, y1 - y0
    face = Face()

    size = logo_h or H * 0.17
    shapes, lw, lh, logo_info = fit_logo(logo, size, W * 0.16, colours, font,
                                         placeholder or "hex", 0.0, 0.0)
    left = x0
    if shapes:
        for slot, polys in shapes.items():
            face.add(slot, "logo", [affinity.translate(p, x0 + lw / 2.0, y1 - lh / 2.0)
                                    for p in polys])
        left = x0 + lw + H * 0.06

    y = y1
    if fields.get("company"):
        polys, _, bh, cap = place_block(fields["company"], font, H * 0.155,
                                        x1 - left, left, y, align="left", anchor="top")
        if polys:
            face.add("primary", "company", polys)
            face.note("company", polys, cap, fields["company"])
            y -= bh + H * 0.04
    if fields.get("role"):
        polys, _, bh, cap = place_block(fields["role"], font, H * 0.075, x1 - left,
                                        left, y, align="left", anchor="top",
                                        tracking=0.04)
        if polys:
            face.add("secondary", "role", polys)
            face.note("role", polys, cap, fields["role"])

    # The bottom eighth is left clear: this layout is drawn to sit on the
    # `badge` pattern, and that is where its band of hexagons goes.
    y = y0 + H * 0.13
    for key, slot, cap_f in (("email", "secondary", 0.075), ("phone", "secondary", 0.085),
                             ("name", "primary", 0.105)):
        if not fields.get(key):
            continue
        polys, _, bh, cap = place_block(fields[key], font, H * cap_f, W * 0.62,
                                        x0, y, align="left", anchor="bottom")
        if polys:
            face.add(slot, key, polys)
            face.note(key, polys, cap, fields[key])
            y += bh + H * 0.035
    return face, logo_info


LAYOUTS = {
    "centred": layout_centred,
    "student": layout_student,
    "corporate": layout_corporate,
}

LAYOUT_TITLES = {
    "centred": "Centred -- name, company, title, rule, phone, email",
    "student": "Student -- name top left, logo square top right, address bottom right",
    "corporate": "Corporate -- mark and company top left, person bottom left",
}

# Which fields each layout has somewhere to put.  The app greys out the rest,
# so the form only ever asks for what the part can actually show.
LAYOUT_FIELDS = {
    "centred": ("name", "company", "role", "phone", "email", "logo"),
    "student": ("name", "role", "company", "email", "phone", "logo"),
    "corporate": ("company", "role", "name", "phone", "email", "logo"),
}


def front_face(spec, w, h, fields, font, logo=None, logo_h=None, design=None,
               colours=None, layout="centred", placeholder=None):
    """The front of the part: whichever layout was asked for, plus the border.

    A `design` -- an SVG, as a path or its text -- replaces all of it: its
    filled shapes cover the whole face, scaled to fill the content box, each
    fill in the file going to the colour slot it is nearest.

    Returns (face, measured, logo_info), where `face` is a Face: polygons by
    (colour slot, field).  Laid out as read; build() mirrors it, because this
    face ends up pointing at the build plate.
    """
    box = content_box(spec, w, h, mirrored=True)
    x0, x1, y0, y1 = box
    logo_info = None

    if design:
        face = Face()
        shapes, dw, dh = logo_polys(design, y1 - y0, x1 - x0, colours)
        for slot, polys in shapes.items():
            face.add(slot, "design",
                     [affinity.translate(p, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
                      for p in polys])
        detail = finest([p for polys in shapes.values() for p in polys])
        logo_info = dict(w=round(float(dw), 1), h=round(float(dh), 1),
                         detail=round(float(detail), 2), nozzle=nozzle_for(detail),
                         design=True, slots=sorted(shapes, key=SLOTS.index))
    else:
        fn = LAYOUTS.get(layout)
        if fn is None:
            raise ValueError(f"no such layout: {layout}")
        face, logo_info = fn(spec, w, h, box, fields, font, logo, logo_h, colours,
                             placeholder)

    if spec["border"]:
        inset = spec["border_inset"]
        face.add("secondary", "border",
                 [frame(w - 2 * inset, h - 2 * inset,
                        max(spec["corner"] - inset, 0.8), spec["border"])])
    return face, face.measured, logo_info


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
            dict(arcs=marks[:n_arcs], tap=marks[n_arcs:], code=code), qr_info)


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
        # A micron of tolerance: enough to drop the doubled vertex a clip can
        # leave behind, which earcut turns into an open mesh; nothing else
        # here is drawn that finely.
        #
        # The second attempt is for a rarer fault, and a stranger one: on some
        # perfectly valid polygons -- a Tektur 'o', an octagon round a square
        # counter -- earcut triangulates the caps with two vertices that are
        # not on the outline, so the caps no longer meet the walls and the
        # solid comes out open.  A hundredth of a micron out and back rebuilds
        # the rings as something it triangulates properly, and moves no corner
        # far enough to see.
        for attempt in (poly.simplify(0.001),
                        poly.buffer(1e-4).buffer(-1e-4).simplify(0.001)):
            mesh = trimesh.creation.extrude_polygon(attempt, thickness)
            if mesh.is_watertight:
                break
        else:
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


def arrange(bounds, gap=6.0, row_w=None):
    """Shifts that lay boxes side by side along x on z = 0, wrapping into
    rows no wider than `row_w`.  `bounds` are (lo, hi) corner pairs."""
    out, x, y, row_h = [], 0.0, 0.0, 0.0
    for lo, hi in bounds:
        pw, ph = hi[0] - lo[0], hi[1] - lo[1]
        if row_w and x > 0 and x + pw > row_w:
            x, y, row_h = 0.0, y - row_h - gap, 0.0
        out.append((x - lo[0], y - hi[1], -lo[2]))
        x += pw + gap
        row_h = max(row_h, ph)
    return out


def layout(parts, gap=6.0, row_w=None):
    """[(part, (dx, dy, dz)), ...]: the parts side by side along x on z = 0,
    wrapping into rows no wider than `row_w` -- a batch on one plate."""
    shifts = arrange([tuple(part["mesh"].bounds) for part in parts], gap, row_w)
    return list(zip(parts, shifts))


def assembled_bounds(part):
    """The corners of a part once it is put back where it sits in the
    finished card."""
    lo, hi = part["mesh"].bounds
    corners = np.array([[x, y, z, 1.0] for x in (lo[0], hi[0])
                        for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    moved = corners @ np.asarray(part["assembled"]).T
    return moved[:, :3].min(axis=0), moved[:, :3].max(axis=0)


def assembly(parts, gap=6.0, row_w=None):
    """[(part, 4x4), ...]: each part's transform into the assembled card, the
    cards laid out side by side the same way the plate is -- what the viewer
    shows when it shows the thing glued up rather than the thing printed."""
    cards = {}
    for part in parts:
        cards.setdefault(part.get("card", 0), []).append(part)
    bounds = []
    for members in cards.values():
        b = [assembled_bounds(m) for m in members]
        bounds.append((np.min([lo for lo, _ in b], axis=0), np.max([hi for _, hi in b], axis=0)))
    out = []
    for members, shift in zip(cards.values(), arrange(bounds, gap, row_w)):
        move = trimesh.transformations.translation_matrix(shift)
        out += [(m, move @ np.asarray(m["assembled"])) for m in members]
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


def export_3mf(parts, colours=COLOURS, gap=6.0, row_w=None):
    """The parts as a 3MF, each colour slot a separate component of one
    object per part, four base materials, so the slicer opens it already
    knowing which filament goes where.

    Written by hand rather than through trimesh's exporter, because what
    matters here is the structure -- one object per part, a component per
    colour, the materials named -- and that is easier to get exactly right
    in forty lines of XML than to coax out of a general-purpose scene writer.
    """
    import io
    import zipfile

    colours = tuple(colours) + tuple(COLOURS[len(colours):])

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
        for pindex, slot in enumerate(SLOTS):
            mesh = part["slots"].get(slot)
            if mesh is None:
                continue
            objects.append(mesh_xml(oid, mesh, pindex, f"{label} {slot}"))
            ids.append(oid)
            oid += 1
        comps = "".join(f'<component objectid="{i}"/>' for i in ids)
        objects.append(f'<object id="{oid}" type="model" name="{label}">'
                       f'<components>{comps}</components></object>')
        items.append(f'<item objectid="{oid}" '
                     f'transform="1 0 0 0 1 0 0 0 1 {dx:.4f} {dy:.4f} {dz:.4f}"/>')
        oid += 1

    bases = "".join(f'<base name="{slot.capitalize()}" displaycolor="{c}"/>'
                    for slot, c in zip(SLOTS, colours))
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        f'<resources><basematerials id="1">{bases}</basematerials>'
        f'{"".join(objects)}</resources>'
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


def flatten(polys):
    out = []
    for p in polys:
        if p.geom_type == "MultiPolygon":
            out += [g for g in p.geoms if g.area > 1e-6]
        elif p.geom_type == "Polygon" and p.area > 1e-6:
            out.append(p)
    return out


def build(kind, name="", company="", phone="", font=None, tag=None,
          tap_text="TAP HERE", tag_mode="split", lid=0.6, border=False, rise=RISE,
          link="", qr=False, logo=None, logo_h=None, chamfer=CHAMFER, label="",
          design=None, look=None, colours=COLOURS, layout="centred", role="",
          email="", placeholder=None):
    """One card or fob as printable parts, plus the numbers worth knowing.

    Returns ([part, ...], info).  Each part is a dict:

      name       "" for a solid body, "front" / "back" for the halves of a
                 split one
      slots      slot name -> solid, for the colours present on this part:
                 "body" is the slab (with its cavity, hole and register pins,
                 and the face cut away wherever another colour goes), the
                 rest are the inlays -- and the raised work, when rise > 0
      mesh       the lot welded into one, for STL
      assembled  4x4 that puts the part back where it sits in the finished,
                 glued-up card (identity for a solid body)

    Keeping the slots apart is what lets export_3mf() hand the slicer four
    colours; the STL gets the welded mesh.

    Every part comes out lying down, face at z = 0, which is how to print it:
    face down gets the build-plate finish, and nothing has to bridge over the
    tag cavity.

    tag_mode picks how the tag goes in:

      split   two half-thickness parts to glue together with the tag
              sandwiched between them, register pins on the joint.  The tag
              ends up on the neutral plane with plastic either side, which is
              the strongest of the three and the only one where nothing of
              the tag shows.  The default.
      pocket  an open recess in the back; stick the tag in afterwards.
      embed   the same recess roofed over with `lid` mm; bury the tag by
              pausing the print at the height this reports.

    `layout` names one of LAYOUTS for the front -- where the name, the logo
    and the rest go.  `role` and `email` are the extra lines the busier
    layouts have room for; `placeholder` ("box" or "hex") draws a stand-in
    where a layout expects a logo and none was given.

    `look` names a background pattern from looks.PATTERNS for the front;
    `colours` are the four the part will print in, used to sort a logo's or
    design's fills into slots.  `logo` is an SVG, as a path or its text, on
    the front beside the name; `design` is an SVG that *is* the front,
    lettering and all (and takes the place of the pattern).  `link` with
    `qr=True` puts a QR code for it on the back.  All three report the nozzle
    they need in info["nozzle"].
    """
    spec = {**BODIES[kind]}
    font = font_path(font)
    t = {**TAG, **(tag or {})}
    if not border:
        spec["border"] = 0.0
    split = tag_mode == "split"
    rise = max(0.0, float(rise))
    rows = qr_matrix(link) if (qr and link) else None
    colours = tuple(colours or COLOURS)

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

    c_eff = max(0.0, min(chamfer, spec["corner"] - 0.2, thick / 2.0 - 0.2))
    outline = rounded_rect(w, h, spec["corner"])

    fields = dict(name=name, company=company, phone=phone, role=role, email=email)
    face, measured, logo_info = front_face(spec, w, h, fields, font, logo, logo_h,
                                           design, colours, layout, placeholder)
    pattern = []
    if look and not design:
        # The pattern fills the face inside the chamfer -- or inside the
        # border, when there is one -- and stays a halo away from everything
        # else on the face, so the lettering reads.
        clip = outline.buffer(-(c_eff + 0.3))
        if spec["border"]:
            inset = spec["border_inset"] + spec["border"] + 1.2
            clip = clip.intersection(rounded_rect(w - 2 * inset, h - 2 * inset,
                                                  max(spec["corner"] - inset, 0.5)))
        if spec["hole"]:
            d = spec["hole"]["d"]
            keep = rounded_rect(d, d, d / 2.0, w / 2.0 - spec["hole"]["wall"] - d / 2.0, 0.0)
            clip = clip.difference(keep.buffer(1.4))    # mirrored side: the front is
        ink = face.ink
        halo = unary_union(ink).buffer(1.25) if ink else None
        pattern = looks.pattern(look, w, h, clip, halo)
        face.add("pattern", "pattern", pattern)
    pocket, marks, qr_info = back_face(spec, w, h, pocket_w, pocket_h, tap_text, font, rows)
    back = {("primary", "arcs"): marks["arcs"], ("primary", "qr"): marks["code"],
            ("secondary", "tap"): marks["tap"]}
    # Both faces are laid out the way you read them.  The back ends up facing
    # +Z and needs nothing done to it; the front faces the build plate, so it
    # is mirrored -- which is exactly what turning the card over does to it.
    front = {key: [affinity.scale(p, -1.0, 1.0, origin=(0, 0)) for p in flatten(polys)]
             for key, polys in face.groups.items() if polys}
    back = {key: flatten(polys) for key, polys in back.items() if polys}

    z_body, z_back = rise, rise + thick     # the front face and back face of the slab

    if split:                   # cavity straddling the joint, half in each part
        z_mid = z_body + thick / 2.0
        cavity, pause_z = (z_mid - depth / 2.0, depth), None
        joint = [round(float(pocket.centroid.x), 3), round(float(pocket.centroid.y), 3),
                 round(float(z_mid), 3)]
    elif tag_mode == "embed":
        cavity, pause_z = (z_back - lid - depth, depth), z_back - lid
        joint = None
    else:
        cavity, pause_z = (z_back - depth, depth + rise + 1.0), None
        joint = None

    cuts = prisms([pocket], *cavity)
    hole = None
    if spec["hole"]:
        d = spec["hole"]["d"]
        hole = rounded_rect(d, d, d / 2.0, -w / 2.0 + spec["hole"]["wall"] + d / 2.0, 0.0)
        cuts += prisms([hole], -1.0, z_back + rise + 2.0)
    # The face layer is cut out of the body wherever another colour goes, and
    # that colour's solid fills the cut, overlapping the body by a hair below
    # it so the STL weld has something to bite on.  Raised work is the same
    # solid carried on past the face.
    for polys in front.values():
        cuts += prisms(polys, z_body - 1.0, 1.0 + FACE)
    for polys in back.values():
        cuts += prisms(polys, z_back - FACE, FACE + 1.0)
    body = boolean("difference", [slab(w, h, spec["corner"], z_body, thick, chamfer), *cuts])

    # One solid per (colour, field): welded within a field, because a logo's
    # shapes can overlap, and left separate between them, because that is what
    # lets the app light up one field at a time.
    front_solids = {key: union(prisms(polys, z_body if key[0] == "pattern" else 0.0,
                                      (FACE + 0.01) + (0.0 if key[0] == "pattern" else rise)))
                    for key, polys in front.items()}
    back_solids = {key: union(prisms(polys, z_back - FACE - 0.01, FACE + 0.01 + rise))
                   for key, polys in back.items()}

    pins = []
    if split:
        blocked = pocket if hole is None else unary_union([pocket, hole])
        pins = register_pins(outline, blocked, w, h)
        parts = halve(body, front_solids, back_solids, z_mid, pins, w, h)
    else:
        parts = [dict(name="", groups=groups(body, front_solids, "front",
                                             back_solids, "back"),
                      assembled=np.eye(4))]
    for part in parts:
        part["label"] = label
        part["card"] = 0
        part["slots"] = slot_meshes(part)
        solids = [part["slots"][s] for s in SLOTS if s in part["slots"]]
        part["mesh"] = solids[0] if len(solids) == 1 else boolean("union", solids)

    arcs = back.get(("primary", "arcs"), [])
    tap = back.get(("secondary", "tap"), [])
    needs = [x["nozzle"] for x in (qr_info, logo_info) if x]
    used = sorted({s for p in parts for s in p["slots"]}, key=SLOTS.index)
    info = dict(
        kind=kind, label=label, w=round(w, 2), h=round(h, 2), thick=thick, rise=rise,
        face=FACE, chamfer=round(c_eff, 2), look=look if pattern else None,
        layout=None if design else layout,
        slots=used, part_slots={p["name"] or kind: sorted(p["slots"], key=SLOTS.index)
                                for p in parts},
        parts=[p["name"] or kind for p in parts], pins=len(pins),
        part_thick=round(rise + (thick / 2.0 if split else thick), 2),
        assembled=round(2 * rise + thick, 2),
        pocket=[round(pocket_w, 2), round(pocket_h, 2), round(depth, 2)],
        tag_mode=tag_mode, lines=measured, logo=logo_info, qr=qr_info,
        # where the tag ends up, in the front half's own coordinates: what a
        # preview needs to draw it sitting in the joint.  Split bodies only.
        joint=joint, tag=[t["w"], t["h"], t["thick"]],
        # None here means a feature is too fine for any nozzle we would name.
        nozzle=(None if any(n is None for n in needs) else min(needs)) if needs else None,
        mark_stroke=round(narrowest(arcs), 2),
        tap_stroke=round(narrowest(tap), 2) if tap else None,
        pattern_stroke=round(narrowest(pattern), 2) if pattern else None,
        pause_z=None if pause_z is None else round(pause_z, 2),
        volume=round(sum(p["mesh"].volume for p in parts) / 1000.0, 2),
        watertight=all(p["mesh"].is_watertight and p["mesh"].is_winding_consistent
                       for p in parts),
        font=Path(font).name,
    )
    info["total_z"] = round(max(p["mesh"].bounds[1][2] for p in parts), 2)
    # Where the colours are, for a part printed face down: every colour in
    # the first `colour_z` mm of the part, the body colour alone above that.
    # A split body has one face per half; a solid one has the back face too,
    # in the last `colour_z` mm.
    info["colour_z"] = round(rise + FACE, 2)
    info["colour_bands"] = ([[0.0, info["colour_z"]]] if split else
                            [[0.0, info["colour_z"]],
                             [round(z_back - FACE, 2), info["total_z"]]])
    info["thin"] = sorted(k for k, v in measured.items() if v["stroke"] < MIN_STROKE)
    if info["tap_stroke"] and info["tap_stroke"] < MIN_STROKE:
        info["thin"].append("tap text")
    return parts, info


def groups(body, *solids_and_faces):
    """A part's drawable pieces, in the order they are welded and sent: the
    slab first, then one group per (colour slot, field, face).

    A group is what the app highlights, what export_3mf() collects by colour
    and what the STL welds into one; keeping them apart here is what lets all
    three have what they need from one build.
    """
    out = [dict(slot="body", element="body", face="body", mesh=body)]
    for solids, which in zip(solids_and_faces[::2], solids_and_faces[1::2]):
        for (slot, element), mesh in solids.items():
            out.append(dict(slot=slot, element=element, face=which, mesh=mesh))
    return out


def slot_meshes(part):
    """The part's groups gathered by colour: what the 3MF's materials want.

    Groups within a slot are disjoint solids in different places on the face,
    so this is a concatenation, not a boolean.
    """
    by_slot = {}
    for g in part["groups"]:
        by_slot.setdefault(g["slot"], []).append(g["mesh"])
    return {slot: (m[0] if len(m) == 1 else trimesh.util.concatenate(m))
            for slot, m in by_slot.items()}


def halve(body, front_solids, back_solids, z_mid, pins, w, h):
    """Cut the slab at the glue joint and hand the front half the pins.

    The inlays need no cutting: the front's lie wholly below the joint and
    the back's wholly above it, so each simply goes with its half.

    The back half is then turned over about Y, so both parts print face down
    with their mating faces up -- pins print as stubs rather than as holes
    needing support, and both halves read the right way up on the plate.  Y
    rather than X because turning it the other way would leave the arcs upside
    down on the build plate; either is the same solid, and either assembles the
    same way, since the pins go back where they started when the half is turned
    over again to glue it.  Each part remembers that move, inverted, as
    `assembled`, so a viewer can show the two glued up.
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
    parts = [dict(name="front", groups=groups(front, front_solids, "front")),
             dict(name="back", groups=groups(back, back_solids, "back"))]
    for part in parts:
        solids = [g["mesh"] for g in part["groups"]]
        move = np.eye(4)
        if part["name"] == "back":
            for m in solids:
                m.apply_transform(flip)
            move = flip @ move
        drop = min(m.bounds[0][2] for m in solids)
        for m in solids:
            m.apply_translation((0.0, 0.0, -drop))
        move = trimesh.transformations.translation_matrix((0.0, 0.0, -drop)) @ move
        part["assembled"] = np.linalg.inv(move)
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
    """Every row as its own part(s), labelled by name; one list, one plate.

    Whatever a row does not carry -- a role, an email -- falls back to the
    setting shared by the whole batch, so the columns stay as they were.
    """
    parts, infos = [], []
    for i, row in enumerate(rows):
        p, info = build(kind, name=row["name"], company=row["company"], phone=row["phone"],
                        link=row["link"] or kw.get("link", ""), label=row["name"],
                        **{k: v for k, v in kw.items() if k != "link"})
        for part in p:
            part["card"] = i
        parts += p
        infos.append(info)
    return parts, infos
