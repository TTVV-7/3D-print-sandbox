"""Name keychains, where the lettering *is* the part.

A card is a slab with wording on it.  A keychain is that the other way round:
the outline comes out of the glyphs, and whatever sits behind them is there to
hold them together.  That one inversion is most of this module -- the text
engine, the extrusion, the colour slots and the 3MF writer all come from
cards.py unchanged, so a keychain downloads as the same four-material 3MF a
card does, with the backing in one filament and the letters in another.

Four backings, in order of how much of the letterform survives as silhouette:

  none      the letters and nothing else, joined only where they touch.  The
            handsome one, and the one that comes off the plate in pieces
            unless the spacing is tight enough to overlap the strokes --
            build() measures that and says so rather than letting you find out
            after an hour of printing.
  outline   the letters, fattened.  One shapely buffer, and the best-looking of
            the four: the backing follows the letterforms instead of boxing
            them in.
  plate     a rounded rectangle behind the lot.  The sturdiest, and the one
            that copes with any font at any size.
  bar       a strip through the middle of the line, ascenders and descenders
            standing out of it.

The handle is what a split ring goes through: nothing, a hole through the
backing, a tab off one end, or a loop on a neck.

Hinges cut the part into segments that come off the plate already linked.
hinge_profiles() is where that lives, and it is worth reading before changing
any of the numbers in HINGE -- the joint is captive in the plane because the
throat is narrower than the head, and captive in Z because the socket is
narrower than the head in the first and last few layers.  Both of those are
differences of well under a millimetre, and a nozzle that cannot hold them
prints a joint that is either fused solid or falls open.
"""
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon
from shapely.geometry import box as box_2d
from shapely.ops import unary_union

import cards
from cards import (QUAD, SLOTS, boolean, extent, flatten, narrowest,
                   nozzle_for, prisms)

# What a keychain is by default: a chunky one, because the failure mode of a
# thin keychain is that it snaps in a pocket.
CAP = 18.0            # capital height, mm -- the size everything scales from
BASE = 3.0            # the backing, and on a hinged one the whole joint
RISE = 1.2            # how far the letters stand off the backing
PAD = 2.5             # buffer for the outline backing, padding for the plate
CORNER = 3.0          # the plate backing's corner radius
LEADING = 1.25        # line spacing, in multiples of the cap height

BACKINGS = ("none", "outline", "plate", "bar")

# The split-ring end.  9 mm of tab round a 4.5 mm hole leaves a 2.25 mm wall,
# which is four lines of a 0.4 nozzle and has never been the thing that broke.
HANDLE = dict(type="tab", position="left", size=9.0, hole=4.5, offset=0.0)
HANDLE_TYPES = ("none", "hole", "tab", "loop")
HANDLE_POSITIONS = ("left", "right", "top")
HANDLE_WALL = 1.8     # least plastic between the ring hole and open air

# Print-in-place hinges.  Every number here is in millimetres except `swing`,
# and every one of them was picked for a 0.4 mm nozzle:
#
#   clearance  the gap on every side of the moving part.  0.45 is a little
#              over one extrusion width, which is the smallest gap that
#              reliably does not fuse.  Under 0.4 it welds itself shut; over
#              0.6 the joint rattles.
#   head/neck  the disc on the end of one segment and the stalk it sits on.
#              The throat the stalk swings in is neck + 2*clearance wide, and
#              the head cannot pass it -- that is the in-plane capture.
#   lip        how much narrower the socket is in the first and last few
#              layers than in the middle.  That overhang, minus the clearance,
#              is what stops the head lifting straight out: at 1.0 and 0.45
#              there is 0.55 mm of plastic over the shoulder of the head.
#   band       how tall those first and last few layers are.  0.6 is three
#              layers at 0.2, enough to be stiff.
#   slot       how far the head can slide along the socket, for "chain".  The
#              strip prints closed up and opens by this much at every joint,
#              so a five-letter chain hangs 6 mm longer than it printed.  Much
#              past 2 mm and the letters read as crowded on the plate.
#   swing      the flare on the mouth, degrees off the joint's axis: how far
#              each segment turns before the stalk touches the side.
HINGE = dict(clearance=0.45, head=6.0, neck=2.4, wall=1.4, lip=1.0, band=0.6,
             slot=1.5, swing=35.0)
HINGE_TYPES = ("none", "pivot", "chain")
HINGE_SLOT = {"pivot": 0.0, "chain": HINGE["slot"]}

def hinge_span(hinge, opts=None):
    """How much gap a joint wants between one letter and the next.

    The socket's ring is head/2 + clearance + wall from its centre, the tile
    behind the stalk stops a clearance short of that, and a chain's slot adds
    its own length -- so the whole assembly is that much either side of the
    gap's middle, plus a millimetre so the tiles end on their own backing
    rather than on a flat cut through a letter.  Under this, a joint eats into
    the letters on both sides of it, which is exactly what it looked like.
    """
    o = {**HINGE, **(opts or {})}
    return 2 * (o["head"] / 2.0 + 2 * o["clearance"] + o["wall"]
                + HINGE_SLOT.get(hinge, 0.0)) + 1.0


# A hinge needs all five bands stacked with something left in the middle for
# the head's shoulder to be, so a backing thinner than this has nowhere to put
# the capture: 2 * (band + clearance) is the floor and 0.5 mm of shoulder is
# the least worth printing.
MIN_HINGE_BASE = 2.6
# and a head smaller than this is not worth calling a hinge.
MIN_HEAD = 3.6


# ---------------------------------------------------------------------------
# the lettering, and what sits behind it
# ---------------------------------------------------------------------------
def lettering(text, font, cap, spacing=0.0, leading=LEADING, align="center"):
    """The glyphs as polygons, centred on the origin, plus what they measure.

    `spacing` is extra letterspacing in millimetres rather than in em, which
    is what anyone setting a keychain actually wants to think in -- and going
    negative with it is how a script face is made to work, by overlapping the
    strokes until the word is one connected piece.
    """
    if not text.strip():
        return [], 0.0, 0.0, 0.0
    tracking = spacing * cards.cap_per_em(font) / cap if cap else 0.0
    polys, w, h, got = cards.text_block(text, font, cap, None, tracking=tracking,
                                        leading=leading, align=align)
    return flatten(polys), w, h, got


def join_pad(ink, pad=PAD, limit=6.0, step=0.25):
    """The smallest outline padding, from `pad` up, that holds the word together.

    An outline backing at a fixed padding is in two pieces about as often as
    it is in one -- a T beside an o leaves a wide gap down at the baseline --
    and two pieces is a keychain that comes off the plate in two pieces.
    Growing the buffer until the letters merge is the fix nobody has to think
    about, and the readout says what it settled on.  Returns `pad` unchanged
    when even the limit will not do it, so the count still reports the truth.
    """
    united = unary_union(ink)
    for i in range(int(limit / step) + 1):
        got = pad + i * step
        if len(flatten([united.buffer(got, quad_segs=QUAD, join_style=1)])) == 1:
            return got
    return pad


def backing_poly(kind, ink, pad=PAD, corner=CORNER):
    """The solid the lettering sits on, or None for `none`."""
    if kind == "none" or not ink:
        return None
    if kind not in BACKINGS:
        raise ValueError(f"no such backing: {kind} -- one of {', '.join(BACKINGS)}")
    united = unary_union(ink)
    if kind == "outline":
        return united.buffer(pad, quad_segs=QUAD, join_style=1)
    x0, y0, x1, y1 = united.bounds
    if kind == "plate":
        return cards.rounded_rect(x1 - x0 + 2 * pad, y1 - y0 + 2 * pad, corner,
                                  (x0 + x1) / 2.0, (y0 + y1) / 2.0)
    # bar: a strip through the middle of the line, sized so it meets every
    # glyph that crosses the midline and lets the rest stand out of it.
    height = max(0.5 * (y1 - y0), 6.0)
    return cards.rounded_rect(x1 - x0 + 2 * pad, height, height / 2.0,
                              (x0 + x1) / 2.0, (y0 + y1) / 2.0)


def edge_point(body, pos, offset=0.0):
    """(a point on the outline, the direction that is "out" from there).

    The corner of a bounding box is often nowhere near the part -- the left of
    a T is the end of its crossbar, three-quarters of the way up -- so a tab
    hung on the box hangs in mid-air, welded to nothing.  This walks the
    material instead and takes the point that is both furthest out and nearest
    the middle of the side it is on, which is where anyone would put a key
    ring by hand.  `offset` moves the middle it aims for.
    """
    if pos not in HANDLE_POSITIONS:
        raise ValueError(f"no such handle position: {pos} -- "
                         f"one of {', '.join(HANDLE_POSITIONS)}")
    x0, y0, x1, y1 = body.bounds
    along = (y0, y1) if pos in ("left", "right") else (x0, x1)
    mid = (along[0] + along[1]) / 2.0 + offset
    best = None
    for t in np.linspace(along[0] + 0.5, along[1] - 0.5, 64):
        strip = (box_2d(-1e4, t - 0.4, 1e4, t + 0.4) if pos in ("left", "right")
                 else box_2d(t - 0.4, -1e4, t + 0.4, 1e4))
        cut = body.intersection(strip)
        if cut.is_empty:
            continue
        b = cut.bounds
        reach = {"left": b[0], "right": -b[2], "top": -b[3]}[pos]
        # A tenth of a millimetre of reach traded for a millimetre nearer the
        # middle: enough to keep the tab off the extreme corner of a letter
        # without letting it drift in to somewhere it would not hang straight.
        score = reach + 0.1 * abs(t - mid)
        if best is None or score < best[0]:
            point = ({"left": (b[0], t), "right": (b[2], t)}.get(pos) or (t, b[3]))
            best = (score, np.array(point, float))
    if best is None:
        raise ValueError("there is no edge to hang a handle from")
    return best[1], np.array({"left": (-1.0, 0.0), "right": (1.0, 0.0),
                              "top": (0.0, 1.0)}[pos])


def handle_shapes(body, spec):
    """(what the handle adds, the hole it cuts).

    The tab and the loop are unioned into the body before anything is cut, so
    a keychain with no backing still has something solid to hang from.
    """
    kind = spec["type"]
    if kind == "none" or body is None or body.is_empty:
        return None, None
    if kind not in HANDLE_TYPES:
        raise ValueError(f"no such handle: {kind} -- one of {', '.join(HANDLE_TYPES)}")
    size, hole = float(spec["size"]), float(spec["hole"])
    if hole + 2 * HANDLE_WALL > size:
        raise ValueError(f"a {hole:.1f} mm hole in a {size:.1f} mm tab leaves "
                         f"{(size - hole) / 2:.2f} mm of wall -- widen the tab to "
                         f"{hole + 2 * HANDLE_WALL:.1f} mm or shrink the hole")

    anchor, out = edge_point(body, spec["position"], float(spec.get("offset", 0.0)))

    if kind == "hole":
        # No tab: the hole goes inside the material, a wall's width in from
        # the edge, which is only sound when there is a backing to put it in.
        centre = anchor - out * (hole / 2.0 + HANDLE_WALL)
        return None, Point(centre).buffer(hole / 2.0, quad_segs=QUAD)

    # A tab sits mostly outside the body and overlaps it by a third of its
    # width, which is enough of a weld that the neck is never the weak point.
    reach = size * (0.32 if kind == "tab" else 0.85)
    centre = anchor + out * reach
    add = Point(centre).buffer(size / 2.0, quad_segs=QUAD)
    if kind == "loop":
        # The neck: a bar from inside the body out to the ring, so the loop
        # stands clear rather than merging into the first letter.
        mid = (anchor + centre) / 2.0
        span = float(np.hypot(*(centre - anchor))) + size / 2.0
        neck = box_2d(-span / 2.0, -size * 0.22, span / 2.0, size * 0.22)
        neck = affinity.rotate(neck, float(np.degrees(np.arctan2(out[1], out[0]))),
                               origin=(0, 0))
        add = unary_union([add, affinity.translate(neck, *mid)])
    return add, Point(centre).buffer(hole / 2.0, quad_segs=QUAD)


# ---------------------------------------------------------------------------
# hinges
# ---------------------------------------------------------------------------
def hinge_span(hinge, opts=None):
    """How much gap a joint wants between one letter and the next.

    The socket's ring is head/2 + clearance + wall from its centre, the tile
    behind the stalk stops a clearance short of that, and a chain's slot adds
    its own length -- so the whole assembly is that much either side of the
    gap's middle, plus a millimetre so the tiles end on their own backing
    rather than on a flat cut through a letter.  Under this, a joint eats into
    the letters on both sides of it, which is exactly what it looked like.
    """
    o = {**HINGE, **(opts or {})}
    return 2 * (o["head"] / 2.0 + 2 * o["clearance"] + o["wall"]
                + HINGE_SLOT.get(hinge, 0.0)) + 1.0


# A hinge needs all five bands stacked with something left in the middle for
# the head's shoulder to be, so a backing thinner than this has nowhere to put
# the capture: 2 * (band + clearance) is the floor and 0.5 mm of shoulder is
# the least worth printing.
MIN_HINGE_BASE = 2.6
# and a head smaller than this is not worth calling a hinge.
MIN_HEAD = 3.6


# ---------------------------------------------------------------------------
# the lettering, and what sits behind it
# ---------------------------------------------------------------------------
def lettering(text, font, cap, spacing=0.0, leading=LEADING, align="center"):
    """The glyphs as polygons, centred on the origin, plus what they measure.

    `spacing` is extra letterspacing in millimetres rather than in em, which
    is what anyone setting a keychain actually wants to think in -- and going
    negative with it is how a script face is made to work, by overlapping the
    strokes until the word is one connected piece.
    """
    if not text.strip():
        return [], 0.0, 0.0, 0.0
    tracking = spacing * cards.cap_per_em(font) / cap if cap else 0.0
    polys, w, h, got = cards.text_block(text, font, cap, None, tracking=tracking,
                                        leading=leading, align=align)
    return flatten(polys), w, h, got


def join_pad(ink, pad=PAD, limit=6.0, step=0.25):
    """The smallest outline padding, from `pad` up, that holds the word together.

    An outline backing at a fixed padding is in two pieces about as often as
    it is in one -- a T beside an o leaves a wide gap down at the baseline --
    and two pieces is a keychain that comes off the plate in two pieces.
    Growing the buffer until the letters merge is the fix nobody has to think
    about, and the readout says what it settled on.  Returns `pad` unchanged
    when even the limit will not do it, so the count still reports the truth.
    """
    united = unary_union(ink)
    for i in range(int(limit / step) + 1):
        got = pad + i * step
        if len(flatten([united.buffer(got, quad_segs=QUAD, join_style=1)])) == 1:
            return got
    return pad


def backing_poly(kind, ink, pad=PAD, corner=CORNER):
    """The solid the lettering sits on, or None for `none`."""
    if kind == "none" or not ink:
        return None
    if kind not in BACKINGS:
        raise ValueError(f"no such backing: {kind} -- one of {', '.join(BACKINGS)}")
    united = unary_union(ink)
    if kind == "outline":
        return united.buffer(pad, quad_segs=QUAD, join_style=1)
    x0, y0, x1, y1 = united.bounds
    if kind == "plate":
        return cards.rounded_rect(x1 - x0 + 2 * pad, y1 - y0 + 2 * pad, corner,
                                  (x0 + x1) / 2.0, (y0 + y1) / 2.0)
    # bar: a strip through the middle of the line, sized so it meets every
    # glyph that crosses the midline and lets the rest stand out of it.
    height = max(0.5 * (y1 - y0), 6.0)
    return cards.rounded_rect(x1 - x0 + 2 * pad, height, height / 2.0,
                              (x0 + x1) / 2.0, (y0 + y1) / 2.0)


def edge_point(body, pos, offset=0.0):
    """(a point on the outline, the direction that is "out" from there).

    The corner of a bounding box is often nowhere near the part -- the left of
    a T is the end of its crossbar, three-quarters of the way up -- so a tab
    hung on the box hangs in mid-air, welded to nothing.  This walks the
    material instead and takes the point that is both furthest out and nearest
    the middle of the side it is on, which is where anyone would put a key
    ring by hand.  `offset` moves the middle it aims for.
    """
    if pos not in HANDLE_POSITIONS:
        raise ValueError(f"no such handle position: {pos} -- "
                         f"one of {', '.join(HANDLE_POSITIONS)}")
    x0, y0, x1, y1 = body.bounds
    along = (y0, y1) if pos in ("left", "right") else (x0, x1)
    mid = (along[0] + along[1]) / 2.0 + offset
    best = None
    for t in np.linspace(along[0] + 0.5, along[1] - 0.5, 64):
        strip = (box_2d(-1e4, t - 0.4, 1e4, t + 0.4) if pos in ("left", "right")
                 else box_2d(t - 0.4, -1e4, t + 0.4, 1e4))
        cut = body.intersection(strip)
        if cut.is_empty:
            continue
        b = cut.bounds
        reach = {"left": b[0], "right": -b[2], "top": -b[3]}[pos]
        # A tenth of a millimetre of reach traded for a millimetre nearer the
        # middle: enough to keep the tab off the extreme corner of a letter
        # without letting it drift in to somewhere it would not hang straight.
        score = reach + 0.1 * abs(t - mid)
        if best is None or score < best[0]:
            point = ({"left": (b[0], t), "right": (b[2], t)}.get(pos) or (t, b[3]))
            best = (score, np.array(point, float))
    if best is None:
        raise ValueError("there is no edge to hang a handle from")
    return best[1], np.array({"left": (-1.0, 0.0), "right": (1.0, 0.0),
                              "top": (0.0, 1.0)}[pos])


def handle_shapes(body, spec):
    """(what the handle adds, the hole it cuts).

    The tab and the loop are unioned into the body before anything is cut, so
    a keychain with no backing still has something solid to hang from.
    """
    kind = spec["type"]
    if kind == "none" or body is None or body.is_empty:
        return None, None
    if kind not in HANDLE_TYPES:
        raise ValueError(f"no such handle: {kind} -- one of {', '.join(HANDLE_TYPES)}")
    size, hole = float(spec["size"]), float(spec["hole"])
    if hole + 2 * HANDLE_WALL > size:
        raise ValueError(f"a {hole:.1f} mm hole in a {size:.1f} mm tab leaves "
                         f"{(size - hole) / 2:.2f} mm of wall -- widen the tab to "
                         f"{hole + 2 * HANDLE_WALL:.1f} mm or shrink the hole")

    anchor, out = edge_point(body, spec["position"], float(spec.get("offset", 0.0)))

    if kind == "hole":
        # No tab: the hole goes inside the material, a wall's width in from
        # the edge, which is only sound when there is a backing to put it in.
        centre = anchor - out * (hole / 2.0 + HANDLE_WALL)
        return None, Point(centre).buffer(hole / 2.0, quad_segs=QUAD)

    # A tab sits mostly outside the body and overlaps it by a third of its
    # width, which is enough of a weld that the neck is never the weak point.
    reach = size * (0.32 if kind == "tab" else 0.85)
    centre = anchor + out * reach
    add = Point(centre).buffer(size / 2.0, quad_segs=QUAD)
    if kind == "loop":
        # The neck: a bar from inside the body out to the ring, so the loop
        # stands clear rather than merging into the first letter.
        mid = (anchor + centre) / 2.0
        span = float(np.hypot(*(centre - anchor))) + size / 2.0
        neck = box_2d(-span / 2.0, -size * 0.22, span / 2.0, size * 0.22)
        neck = affinity.rotate(neck, float(np.degrees(np.arctan2(out[1], out[0]))),
                               origin=(0, 0))
        add = unary_union([add, affinity.translate(neck, *mid)])
    return add, Point(centre).buffer(hole / 2.0, quad_segs=QUAD)


# ---------------------------------------------------------------------------
# hinges
# ---------------------------------------------------------------------------
def column_gaps(ink):
    """The clear vertical lanes between letters, as (centre, width).

    Glyph boxes that overlap in x -- a script face, or an accent over its
    letter -- are merged first, so what comes back is the gaps a knife could
    actually go through without touching ink.
    """
    spans = sorted((p.bounds[0], p.bounds[2]) for p in ink)
    merged = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [((a[1] + b[0]) / 2.0, b[0] - a[1]) for a, b in zip(merged, merged[1:])]


def columns(ink):
    """The glyphs grouped into the columns they stand in, left to right.

    Each column is (polygons, x0, x1, y0, y1).  Shapes that overlap in x -- an
    accent over its letter, or two glyphs of a joined-up face -- are one
    column, because a knife could not pass between them and neither can a
    joint.
    """
    out = []
    for poly in sorted(ink, key=lambda p: p.bounds[0]):
        x0, y0, x1, y1 = poly.bounds
        if out and x0 <= out[-1][2]:
            got = out[-1]
            out[-1] = (got[0] + [poly], got[1], max(got[2], x1),
                       min(got[3], y0), max(got[4], y1))
        else:
            out.append(([poly], x0, x1, y0, y1))
    return out


def weld_band(left, right, pad):
    """How much of a band two neighbouring columns have in common where they
    face each other, once each has its outline backing round it.

    Measured the way joint_at() measures it -- a couple of millimetres into
    each tile, not across the whole letter -- because that is where the stalk
    has to land.  A T beside an o overlap over the whole x-height on paper;
    what actually faces the o is the end of the crossbar, three quarters of
    the way up, and a millimetre of it lines up with anything.  Shifting the
    columns apart in x does not change any of that, so this can be asked
    before they are laid out.
    """
    out = []
    for col, way in ((left, 1.0), (right, -1.0)):
        shape = unary_union(col[0]).buffer(pad, quad_segs=QUAD, join_style=1)
        face = shape.bounds[2] if way > 0 else shape.bounds[0]
        lo, hi = sorted((face, face - way * INTO_TILE))
        pieces = flatten([shape.intersection(box_2d(lo, -1e4, hi, 1e4))])
        if not pieces:
            return 0.0
        big = max(pieces, key=lambda p: p.area)
        out.append((big.bounds[1], big.bounds[3]))
    return min(out[0][1], out[1][1]) - max(out[0][0], out[1][0])


def spread_for_hinges(ink, want, span, pad, backing="outline", opts=None):
    """(the lettering laid out with room for its joints, where the joints go).

    Letters set for reading stand a millimetre or two apart and a joint wants
    ten, so the gaps that are going to hold one are opened to `span` and every
    other gap is left exactly as it was.  That second half matters as much as
    the first: open all of them and a link carrying two letters is two tiles
    with nothing between them, which prints as two tiles.

    A gap can only hold a joint where the letters either side of it overlap
    enough for a socket to be held at both ends -- a T beside a comma do not --
    so those gaps are never chosen and never opened, and the two letters ride
    on one tile.
    """
    cols = columns(ink)
    if len(cols) < 2:
        raise ValueError("there is no gap between letters here to put a joint in "
                         "-- open the letter spacing up, or pick a face whose "
                         "letters do not join into one another")
    o = {**HINGE, **(opts or {})}
    # The same question hinge_profiles asks: is there a band these two letters
    # have in common wide enough to weld a stalk across?  How *tall* the tiles
    # are only decides how big the ring may be, so it is not asked here.
    need = o["neck"] + 2 * o["clearance"]
    # A plate or a bar runs the whole length behind the letters, so every gap
    # in one has the full height of the backing to weld across.  Only the
    # outline has tiles that end where the letters do.
    viable = [i for i in range(len(cols) - 1)
              if backing != "outline"
              or weld_band(cols[i], cols[i + 1], pad) >= need]
    if not viable:
        raise ValueError("no two letters here stand level with each other for long "
                         "enough to hold a joint between them -- try a plate backing")

    # A gap the backing does not bridge on its own -- the space between two
    # words, most often -- is already two tiles, so it *has* to have a joint
    # whether or not the link count asked for one.  Anything else is a choice.
    must = [] if backing != "outline" else [
        i for i in range(len(cols) - 1) if cols[i + 1][1] - cols[i][2] >= 2 * pad]
    short = [i for i in must if i not in viable]
    if short:
        raise ValueError("the letters either side of a gap this wide have to hold a "
                         "joint between them, and here they do not stand level "
                         "enough to -- close the letter spacing, or put a plate "
                         "behind it")

    k = max(len(must) + 1, 2)
    k = max(k, min(int(want) if int(want or 0) >= 2 else len(cols), len(viable) + 1))
    free, picks = [i for i in viable if i not in must], list(must)
    for i in range(1, k):                       # spread the rest over the word
        if len(picks) >= k - 1 or not free:
            break
        pick = min(free, key=lambda g: abs((g + 1) - i * len(cols) / k))
        free.remove(pick)
        picks.append(pick)
    picks = set(picks)

    out, cuts, shift = [], [], 0.0
    for j, col in enumerate(cols):
        out += [affinity.translate(poly, shift, 0.0) for poly in col[0]]
        if j in picks:
            gap = cols[j + 1][1] - col[2]
            grow = max(0.0, span - gap)
            cuts.append(col[2] + shift + (gap + grow) / 2.0)
            shift += grow
    return out, cuts


# How far a stalk or an arm reaches past the edge of the tile it joins, and how
# far in the band it has to fit is measured.  The leading edge of a rounded
# outline is a sliver a fraction of a millimetre tall: weld to that and the
# joint hangs off a corner, size a socket on it and the socket fits nothing.
INTO_TILE = 2.5


INTO_BODY = 8.0          # and how far in the tile is measured for its height


def band_near(outline, x, step, reach=14.0):
    """(where, the band to weld to, the band to size against) for the nearest
    tile to `x` in direction `step`.

    Two bands, because they answer different questions.  The near one, a
    couple of millimetres into the tile, is where a stalk has to land to be
    welded to anything.  The wide one, most of a centimetre in, is how tall
    the tile really is -- and sizing a socket on the near band instead gets a
    socket sized on the tip of a K, which is nothing at all.
    """
    way = 1.0 if step > 0 else -1.0

    def band(depth):
        lo, hi = sorted((at, at + way * depth))
        pieces = flatten([outline.intersection(box_2d(lo, -1e4, hi, 1e4))])
        big = max(pieces, key=lambda p: p.area)
        return big.bounds[1], big.bounds[3]

    for d in np.arange(0.0, reach + abs(step), abs(step)):
        at = x + way * d
        if not flatten([outline.intersection(box_2d(at - 0.15, -1e4, at + 0.15, 1e4))]):
            continue
        return float(at), band(INTO_TILE), band(INTO_BODY)
    return None


def joint_at(outline, x):
    """(centre, height) of the material a joint at `x` has to fit between.

    Once the letters are spaced for hinges there is nothing at all at `x` --
    it is the gap -- so this measures the near end of the tile on each side
    and takes the band they have in common, which is the only height a joint
    can sit at and be held at both ends.  Where the backing runs straight
    through, both measurements land on the same strip and it comes to the
    same thing.
    """
    left, right = band_near(outline, x, -0.5), band_near(outline, x, 0.5)
    if left is None or right is None:
        raise ValueError(f"nothing to hinge at x = {x:.1f} mm")
    weld = (max(left[1][0], right[1][0]), min(left[1][1], right[1][1]))
    if weld[1] - weld[0] <= 0:
        raise ValueError(f"the two sides of x = {x:.1f} mm do not stand level "
                         "with each other")
    y = (weld[0] + weld[1]) / 2.0
    # How much room there is, measured about the height the joint will sit at
    # rather than about the middle of anything: a socket centred low down has
    # the tile below it to fit into, not the tile's whole height.
    wide = (max(left[2][0], right[2][0]), min(left[2][1], right[2][1]))
    room = 2.0 * min(y - wide[0], wide[1] - y)
    return np.array([x, y]), room, weld[1] - weld[0], left[0], right[0]


def hinge_profiles(centre, height, slot, opts, left_x=None, right_x=None,
                   weld=None):
    """The 2-D pieces of one joint, and the head it settled on.

    Returns a dict of polygons.  `head_*` and `neck` belong to the segment on
    the left; `ring`, the two cavities and `mouth` to the one on the right.
    Each comes in two widths, and the difference between them is the trick:

        wide    a head of `head` diameter in a cavity of head + 2*clearance
        narrow  a head of head - 2*lip in a cavity of head - 2*lip + 2*clearance

    so the socket's inner edge, where it is narrow, stands `lip - clearance`
    inside the widest part of the head.  Stack them -- socket narrow at the
    bottom and the top, head wide only in the middle -- and lifting the head
    out means raising it clear of the top lip, which is base - band -
    clearance: about 2 mm of the 3 mm the backing is thick.  That is far more
    than a pocket will ever do to it and much less than forever, which is the
    honest way to put it.  In the plane it is properly captive: the throat is
    neck + 2*clearance wide against a head of `head`, and no amount of pulling
    gets one through the other.  Nothing is glued and nothing is assembled.

    The two do not change width at the same height: the socket goes wide at
    `band` and the head at `band + clearance`, which is what puts a real gap
    between the underside of the socket's lip and the top of the head's
    shoulder.  Without it those two faces meet exactly, and a joint whose
    parts share a plane is a joint the boolean -- and then the slicer -- welds
    solid.  That is the one mistake here that still looks right on screen.
    """
    o = {**HINGE, **(opts or {})}
    c, wall, lip = o["clearance"], o["wall"], o["lip"]
    neck = o["neck"]

    # Two different questions, and only one of them can refuse.
    #
    # `height` is how tall the tiles are where the joint meets them, and all it
    # decides is how big the ring may be before it stands out past the letters.
    # It is a matter of looks, not of soundness -- the ring sits in the gap,
    # where there is nothing for it to foul -- so a short one shrinks the head
    # and, below the smallest head worth the name, simply lets it overhang.
    #
    # `weld` is the band the two tiles have in common at the joint, and that
    # one is structural: no overlap, no stalk, and the head is welded to air.
    head = max(MIN_HEAD, min(float(o["head"]),
                             max(0.0, height - 0.8) - 2 * (c + wall)))
    # The stalk shrinks with the head it carries.  Left at full width while the
    # head came down it ended up wider than the cavity the head sits in, and
    # the socket closed onto it with fifty microns to spare -- which prints as
    # one solid piece.  The lip does *not* scale: it is what holds the head
    # down, and lip minus clearance is the whole of that grip.
    neck *= head / float(o["head"])
    if weld is not None and weld < neck + 2 * c:
        raise ValueError(
            f"the letters either side of this joint only stand level with each "
            f"other for {weld:.1f} mm, and a stalk needs {neck + 2 * c:.1f} -- "
            f"ask for fewer links, or put a plate behind it")
    r = head / 2.0
    p = np.asarray(centre, float)            # where the head is drawn
    q = p - [slot, 0.0]                      # the mouth end of the socket
    disc = lambda at, rad: Point(at).buffer(rad, quad_segs=QUAD)
    span = lambda rad: unary_union([disc(p, rad), disc(q, rad),
                                    box_2d(q[0], p[1] - rad, p[0], p[1] + rad)])

    # The socket runs from the mouth *away* from the segment the stalk comes
    # from, and the head is drawn at the far end of it, so the strip prints at
    # its shortest and every joint can open by `slot`.  Drawn the other way
    # round the slot buys nothing: the segments are already touching and the
    # only way the head could slide is into its neighbour.
    throat = neck / 2.0 + c
    reach = r + c + wall + c + 0.5          # past the far side of the ring
    flare = np.tan(np.radians(o["swing"]))
    lip_out = throat + (reach - (r + c)) * flare
    mouth = Polygon([
        (p[0], p[1] + throat), (q[0] - (r + c), p[1] + throat),
        (q[0] - reach, p[1] + lip_out), (q[0] - reach, p[1] - lip_out),
        (q[0] - (r + c), p[1] - throat), (p[0], p[1] - throat)])

    edge = q[0] - (r + c + wall) - c        # where the left segment stops

    # Both halves of the joint sit in the gap between two letters, which is
    # wider than either of them: the stalk has to reach back to the tile it
    # hangs from and the ring has to reach forward to the tile it belongs to.
    # Without that arm the ring prints as a loose washer lying in the gap --
    # which is exactly what it did, and it looked right on screen.
    start = min(edge, left_x if left_x is not None else edge) - INTO_TILE
    ring = span(r + c + wall)
    if right_x is not None and right_x + INTO_TILE > p[0]:
        ring = unary_union([ring, box_2d(p[0], p[1] - (neck / 2.0 + wall),
                                         right_x + INTO_TILE,
                                         p[1] + (neck / 2.0 + wall))])
    return dict(
        head_wide=disc(p, r), head_narrow=disc(p, r - lip),
        cav_wide=span(r + c), cav_narrow=span(r - lip + c),
        ring=ring.buffer(0),
        neck=box_2d(start, p[1] - neck / 2.0, p[0], p[1] + neck / 2.0),
        mouth=mouth, edge=edge, head=head, band=o["band"],
        clear=c)


# A piece of backing smaller than this that a socket has pinched off is debris,
# not geometry: it prints as a loose fleck inside the joint, where it jams the
# hinge.  Anything bigger is left where it is and reported instead.
DEBRIS = 8.0


def one_piece(shape):
    """(the shape without its specks, how many were dropped)."""
    parts = flatten([shape])
    if len(parts) < 2:
        return shape, 0
    big = max(parts, key=lambda p: p.area)
    keep = [p for p in parts if p is big or p.area >= DEBRIS]
    return unary_union(keep), len(parts) - len(keep)


def segment_profiles(outline, joints, base, band, clear):
    """[[(z0, thickness, shape), ...]] -- each segment as a stack of slices,
    bottom to top, plus how many specks were swept out of the joints.

    Five slices, because the socket and the head change width at different
    heights (see hinge_profiles):

        0        .. band            socket narrow, head narrow
        band     .. band+clear      socket wide,   head narrow   <- the gap
        band+c   .. base-band-c     socket wide,   head wide
        ...                         and back down the same way

    A segment holds the socket of the joint on its left and the head of the
    joint on its right, so the two ends of the strip have one each and every
    segment in between has both.
    """
    lo, _, hi, _ = outline.bounds
    levels = [(0.0, band, "narrow", "narrow"),
              (band, band + clear, "narrow", "wide"),
              (band + clear, base - band - clear, "wide", "wide"),
              (base - band - clear, base - band, "narrow", "wide"),
              (base - band, base, "narrow", "narrow")]
    if any(z1 - z0 < 0.05 for z0, z1, _, _ in levels):
        raise ValueError(f"a {base:.1f} mm backing has no room for a hinge's "
                         f"capture -- it needs more than {2 * (band + clear):.1f} mm")

    stacks, swept = [], 0
    for i in range(len(joints) + 1):
        left = joints[i - 1] if i else None
        right = joints[i] if i < len(joints) else None
        x_lo = left["centre"][0] if left else lo - 1.0
        x_hi = right["edge"] if right else hi + 1.0
        region = outline.intersection(box_2d(x_lo, -1e4, x_hi, 1e4))

        def profile(head, cav):
            add = [region]
            if left:
                add.append(left["ring"])
            if right:
                add += [right["neck"], right[f"head_{head}"]]
            shape = unary_union(add)
            if left:
                # The cavity and the channel out of it are voids in *this*
                # segment's socket.  They are not subtracted at the other end:
                # the channel is exactly where the next segment's stalk lives,
                # and cutting it out of the stalk as well leaves the head
                # floating free -- which is what it did, the first time.
                shape = shape.difference(left[f"cav_{cav}"]).difference(left["mouth"])
            return shape

        slices, dropped = [], 0
        for z0, z1, head, cav in levels:
            shape, n = one_piece(profile(head, cav))
            dropped = max(dropped, n)
            slices.append((z0, z1 - z0, shape))
        swept += dropped
        stacks.append(slices)
    return stacks, swept


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def build(text="Keychain", font=None, cap=CAP, spacing=0.0, leading=LEADING,
          align="center", backing="outline", pad=PAD, corner=CORNER, base=BASE,
          rise=RISE, handle=None, hinge="none", segments=0, hinge_opts=None,
          join=True, colours=None, label=""):
    """One keychain as printable parts, plus the numbers worth knowing.

    Returns ([part, ...], info) in exactly the shape cards.build() does, so
    the same preview, STL, plate and 3MF code serves both.  A keychain is
    always one part: even a hinged one prints as a single object, because the
    segments come out of the printer already linked and moving them apart on
    the plate would be moving them out of their hinges.

    The colours are the first two slots -- the backing is "body" and the
    letters are "primary" -- so a two-material printer needs one change, at
    the top of the backing.

    `hinge` is "pivot" or "chain" and `segments` how many pieces to cut the
    strip into; 0 asks for one per letter.  Both need a backing: bare letters
    have no material at the joints to put a hinge in.
    """
    font = cards.font_path(font)
    cap = max(4.0, float(cap))
    base = max(0.8, float(base))
    rise = max(0.0, float(rise))
    spec = {**HANDLE, **(handle or {})}
    colours = tuple(colours or cards.COLOURS)

    if hinge not in HINGE_TYPES:
        raise ValueError(f"no such hinge: {hinge} -- one of {', '.join(HINGE_TYPES)}")
    hinged = hinge != "none"
    if hinged and backing == "none":
        raise ValueError("a hinge needs a backing to sit in -- pick outline, "
                         "plate or bar, or turn the hinge off")
    if hinged and base < MIN_HINGE_BASE:
        raise ValueError(f"a hinged joint needs a backing at least "
                         f"{MIN_HINGE_BASE:.1f} mm thick to fit the capture in; "
                         f"this one is {base:.1f} mm")

    ink, ink_w, ink_h, cap_got = lettering(text, font, cap, spacing, leading, align)
    if not ink:
        raise ValueError("there is no text to make a keychain out of")

    # Settled before anything is spread apart, so the padding that joins two
    # letters into one tile is chosen against the spacing they were set at
    # rather than against a gap that is about to hold a joint.
    if backing == "outline" and join:
        pad = join_pad(ink, pad)

    cuts = []
    if hinged:
        if len([ln for ln in text.replace("|", "\n").split("\n") if ln.strip()]) > 1:
            raise ValueError("a hinged keychain is one line of letters -- the links "
                             "run left to right, and a second line has no chain to "
                             "be part of")
        ink, cuts = spread_for_hinges(ink, segments, hinge_span(hinge, hinge_opts),
                                      pad, backing, hinge_opts)
        x0, _, x1, _ = extent(ink)
        ink = [affinity.translate(poly, -(x0 + x1) / 2.0, 0.0) for poly in ink]
        cuts = [x - (x0 + x1) / 2.0 for x in cuts]
        ink_w = x1 - x0
    body = backing_poly(backing, ink, pad, corner)
    add, hole = handle_shapes(body if body is not None else unary_union(ink), spec)

    # Whatever the handle adds joins the backing when there is one and the
    # letters when there is not, so the tab is the same colour as the thing it
    # grows out of either way.
    if body is not None:
        outline = unary_union([body] + ([add] if add is not None else []))
        letters = unary_union(ink)
    else:
        outline = None
        letters = unary_union(ink + ([add] if add is not None else []))

    # What the letters and the backing actually are, once the ring hole is out
    # of them.  The hole goes through everything: cut it from both.
    if hole is not None:
        if outline is not None:
            outline = outline.difference(hole)
        letters = letters.difference(hole)

    joints, segs, swept = [], 1, 0
    if hinged:
        slot = HINGE_SLOT[hinge]
        for x in cuts:
            centre, height, weld, left_x, right_x = joint_at(outline, x)
            joints.append({**hinge_profiles(centre, height, slot, hinge_opts,
                                            left_x, right_x, weld),
                           "centre": centre})
        segs = len(cuts) + 1

    # ------------------------------------------------------------------ mesh
    band = joints[0]["band"] if joints else 0.0
    solids, pieces = {}, []
    if joints:
        # The slices meet on exact planes and never overlap, not even by ten
        # microns: an overlap between the band where the head is at its widest
        # and the band where the socket is at its narrowest welds every joint
        # on the chain solid, and the model still looks right on screen.
        shapes, swept = segment_profiles(outline, joints, base, band,
                                         joints[0]["clear"])
        back = []
        for slices in shapes:
            pieces.append(slices[0][2])          # what it stands on
            for z0, thickness, shape in slices:
                back += prisms(flatten([shape]), z0, thickness)
        solids[("body", "backing")] = cards.union(back)
        # Letters are clipped to the top of the segment they stand on, so
        # nothing bridges a joint and glues the chain shut.
        keep = unary_union([s[-1][2] for s in shapes]).buffer(-0.01)
        letters = letters.intersection(keep)
    elif outline is not None:
        pieces = flatten([outline])
        solids[("body", "backing")] = cards.union(prisms(pieces, 0.0, base))

    ink_z = base - 0.01 if outline is not None else 0.0
    ink_t = (rise + 0.01) if outline is not None else (base + rise)
    # Clipping the lettering to its segment, and cutting the ring hole, both
    # leave slivers now and then -- the tail of a Y on the wrong side of a
    # joint.  A sliver narrower than a nozzle prints as a wisp or as nothing,
    # so it goes the same way the backing's specks do.
    ink_polys, wisps = [], 0
    for poly in flatten([letters]):
        if poly.area < 0.8 or cards.stroke_width(poly) < 0.4:
            wisps += 1
        else:
            ink_polys.append(poly)
    swept += wisps
    if not ink_polys:
        raise ValueError("the ring hole has eaten the lettering -- move the handle")
    if outline is None:
        pieces = ink_polys
    if ink_t > 0.005:
        solids[("primary" if outline is not None else "body", "letters")] = \
            cards.union(prisms(ink_polys, ink_z, ink_t))

    # A group per (colour slot, element): the backing first, then the letters,
    # which is the order they print in and the order the viewer draws them.
    part = dict(name="", label=label, card=0, assembled=np.eye(4),
                groups=[dict(slot=slot, element=element, face="front", mesh=mesh)
                        for (slot, element), mesh in _ordered(solids)])
    part["slots"] = cards.slot_meshes(part)
    stack = [part["slots"][s] for s in SLOTS if s in part["slots"]]
    part["mesh"] = stack[0] if len(stack) == 1 else boolean("union", stack)

    # ------------------------------------------------------------------ info
    # Everything that is printed, backing and lettering together: what the
    # part measures, and -- counting the pieces it falls into against the
    # number of segments there should be -- whether it comes off the plate in
    # one piece or several.  A loose letter is the failure mode of a keychain
    # with no backing, and finding out here beats finding out in an hour.
    whole = unary_union(pieces + ink_polys)
    x0, y0, x1, y1 = whole.bounds
    # Measured on the glyphs as the font drew them, not on what is left of
    # them after a joint has cut one in half: the question the number answers
    # is whether this face at this size prints, and half a letter is not a
    # stroke anybody chose.
    stroke = narrowest(ink)
    loose = len(flatten([whole])) - (segs if joints else 1)
    info = dict(
        kind="keychain", label=label or "keychain", text=text,
        w=round(x1 - x0, 2), h=round(y1 - y0, 2),
        thick=round(base + rise, 2), base=round(base, 2), rise=round(rise, 2),
        cap=round(cap_got, 2), backing=backing, pad=round(pad, 2),
        handle=spec["type"], handle_hole=round(float(spec["hole"]), 2)
        if spec["type"] != "none" else None,
        hinge=hinge if joints else "none", segments=segs if joints else 1,
        cuts=[round(float(x), 2) for x in cuts],
        letters=len(columns(ink)), spacing=round(spacing, 2),
        hinge_head=round(joints[0]["head"], 2) if joints else None,
        hinge_clearance=round({**HINGE, **(hinge_opts or {})}["clearance"], 2)
        if joints else None,
        hinge_band=round(band, 2) if joints else None, swept=swept,
        hinge_lift=round(base - band - joints[0]["clear"], 2) if joints else None,
        slots=sorted(part["slots"], key=SLOTS.index),
        part_slots={"keychain": sorted(part["slots"], key=SLOTS.index)},
        parts=["keychain"], stroke=round(stroke, 2),
        nozzle=nozzle_for(stroke), loose=max(0, loose),
        font=Path(font).name, lines=len([l for l in text.replace("|", "\n").split("\n")
                                         if l.strip()]),
        volume=round(float(part["mesh"].volume) / 1000.0, 2),
        watertight=bool(part["mesh"].is_watertight
                        and part["mesh"].is_winding_consistent),
        total_z=round(base + rise, 2), colour_z=round(base + rise, 2),
        colour_bands=[[0.0, round(base + rise, 2)]],
        thin=["the lettering"] if stroke < cards.MIN_STROKE else [],
        logo=None, qr=None, batch=0,
    )
    return [part], info


def _ordered(solids):
    """The part's solids in the order they print: backing, then lettering."""
    order = [("body", "backing"), ("primary", "letters"), ("body", "letters")]
    return [(k, solids[k]) for k in order if k in solids]
