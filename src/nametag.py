"""A name keyring: the letters themselves are the object.

No plate to sit on and nothing to hold but the word -- so the whole problem is
that a word is not one thing.  Set "Freddie" in any font and you get seven
separate solids, and seven separate solids is seven pieces off the print bed.
This welds them into one:

  1. the letters are set by eye rather than by the font's own spacing: each
     one is walked left until its ink is a hair from its neighbour's, which is
     what a sign painter does and what the font's side bearings -- built for
     running text on a page -- will not give you;
  2. every glyph is grown outward by `weld` mm and the lot unioned, which
     closes the gaps that are left and fattens the thin strokes while it is
     there -- that outward step is also the small outline you can see round
     the letters on every shop-bought one of these.  Growing a letter shuts
     its counter -- the hole in an a, e or o -- by the same amount, so the
     counters are cut back in afterwards and only the outside stays fat;
  3. whatever is still loose after that -- the dot of an i, which is its own
     contour floating over the stem, or the two halves of "L I" -- is tied on
     with a bridge: a bar as wide as two extrusion lines, run along the
     shortest line between the piece and the word.  Bridging one dot beats
     welding the whole name fat enough to catch it.

What comes out is one solid in the shape of the word, with the letters raised
on top of it in a second colour, and a ring tab at the left for the split ring.

    parts, info = nametag.build("Freddie")

The parts are the same shape as cards.build()'s, so the plate layout, the 3MF,
the STL and the app's viewer all take them unchanged.
"""
import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union

import cards

# The letters, in millimetres of capital height.  14 mm is about the size of
# the ones on a keyring at a school fair: big enough to read across a table,
# small enough not to bruise a leg through a pocket.
CAP = 14.0

# A keyring gets dropped, sat on and jangled against keys, so it is thicker
# than anything else here: 3 mm of body with the letters 1.2 mm proud of it.
THICK = 3.0
RISE = 1.2

# How far each glyph grows before the union.  This is the number that decides
# whether the word holds together, and it is also the visible outline round
# the letters.  Too little and the word comes apart; too much and the counters
# -- the holes in a, e, o -- close up.
WELD = 0.5

# The tie that catches whatever the weld did not.  1.2 mm is three lines of a
# 0.4 mm nozzle: thin enough to read as a join rather than a stroke, thick
# enough to survive a keyring.
BRIDGE = 1.2
BRIDGE_MAX = 24         # a runaway loop would be a bug, not a name

# How close the ink of one letter is walked to the ink of the last.  Slightly
# negative, so they overlap and the word is one piece before the weld is asked
# to do anything about it.
GAP = -0.15
KERN_STEP = 3           # passes of the walk; the distance is not linear in x

# A void this small, or this narrow, is not a counter -- it is a crack the
# weld left between two letters.  Neither can print: the slicer bridges a gap
# under a nozzle wide and fills a hole it cannot fit a perimeter into, so a
# model that keeps them only lies about what comes out.  Filled in, and the
# reported counter size is then the smallest hole that is really there.
MIN_VOID = 1.5          # mm^2
MIN_VOID_W = 0.7        # mm across

# The tab at the left, and the hole through it.  5 mm takes a split ring or a
# lobster clasp; 2.2 mm of plastic round it is what stops it tearing out.
RING_D = 5.0
RING_WALL = 2.2

# A counter this size or smaller has stopped being a hole and become a dimple,
# and the slicer will bridge it.  Reported, not refused: on a big name it never
# happens, and on a small one it is the user's call.
MIN_COUNTER = 1.2


def glyph(ch, font, cap):
    """One character, `cap` mm tall, on the baseline and starting at x = 0."""
    shapes = cards.trace_text.trace(ch, font)
    if not shapes:
        return []
    k = cap / cards.cap_per_em(font)
    shapes = [affinity.scale(s, k, k, origin=(0, 0)) for s in shapes]
    x0, _, _, _ = cards.extent(shapes)
    return [affinity.translate(s, -x0, 0.0) for s in shapes]


def glyphs(text, font, cap=CAP, gap=GAP):
    """The letters of `text`, set tight: each walked left until its ink is
    `gap` from the last letter's ink.

    The font's own advance is only the starting point.  It is measured for a
    page, where "LT" wants air between the L's foot and the T's arm; on a
    keyring the two want to touch, because touching is what makes the word one
    printable piece.  So the placement is by ink: put the letter down a whisker
    clear, then walk it in until shapely says the gap is right.  Three passes,
    because the distance between two letterforms is not linear in x and one
    step overshoots on a diagonal.
    """
    placed, pen = [], 0.0
    for ch in text:
        if ch.isspace():
            pen += cap * 0.32
            continue
        shape = glyph(ch, font, cap)
        if not shape:
            continue
        shape = [affinity.translate(s, pen, 0.0) for s in shape]
        if placed:
            last = unary_union(placed)
            for _ in range(KERN_STEP):
                here = unary_union(shape)
                d = last.distance(here)
                if d <= 0:                      # already touching: leave it
                    break
                shift = -(d - gap)
                shape = [affinity.translate(s, shift, 0.0) for s in shape]
        placed += shape
        _, _, x1, _ = cards.extent(shape)
        pen = x1 + max(gap, 0.0)
    if not placed:
        raise ValueError("nothing to set: give it a name")
    x0, _, _, _ = cards.extent(placed)
    return [affinity.translate(s, -x0, 0.0) for s in placed]


def fill_cracks(poly, least=MIN_VOID):
    """The same shape with its slivers of trapped air filled in.

    Welding two letters together traps a little wedge of nothing between them.
    It is under a nozzle wide, so it prints as solid anyway; leaving it in the
    model only means a hole in the mesh that no printer will honour and a
    counter measurement that reads as though the a had closed up.
    """
    def real(ring):
        hole = cards.Polygon(ring)
        return hole.area >= least and cards.stroke_width(hole) >= MIN_VOID_W

    def keep(p):
        return cards.Polygon(p.exterior, [r for r in p.interiors if real(r)])
    if poly.geom_type == "MultiPolygon":
        return unary_union([keep(g) for g in poly.geoms])
    return keep(poly)


def tie_together(poly, width=BRIDGE):
    """(one polygon, bridges added): ties every loose piece to the main one.

    Each pass takes the biggest piece, finds whichever other piece comes
    nearest it, and runs a bar of `width` along the line between them.  The
    bar is round-capped, so even a piece already touching at a point -- which
    unions to a shape whose boundary crosses itself and will not extrude --
    ends up with real overlap.
    """
    ties = 0
    while poly.geom_type == "MultiPolygon" and ties < BRIDGE_MAX:
        pieces = sorted(poly.geoms, key=lambda g: -g.area)
        base, rest = pieces[0], pieces[1:]
        near = min(rest, key=base.distance)
        a, b = nearest_points(base, near)
        poly = unary_union([poly, LineString([a, b]).buffer(width / 2.0,
                                                           cap_style=1, quad_segs=8)])
        ties += 1
    return poly, ties


def weld_together(shapes, weld=WELD, bridge=BRIDGE):
    """(one polygon, the weld, the number of bridges it took).

    The counters are put back after the weld.  Growing a glyph outward shrinks
    its counter by the same amount, and a name is unreadable with filled-in
    a's; cutting the original holes back in leaves the fat outline where it is
    wanted, on the outside.
    """
    holes = unary_union([cards.Polygon(r) for s in shapes for r in s.interiors])
    merged = unary_union([s.buffer(weld, quad_segs=8, join_style=1) for s in shapes])
    if not holes.is_empty:
        # keep a little of the weld inside the counter, so the ring round it
        # still reads as an outline rather than the bare letter
        keep = holes.buffer(-min(weld * 0.45, 0.4))
        if not keep.is_empty:
            merged = merged.difference(keep)
    merged, ties = tie_together(merged, bridge)
    return fill_cracks(merged), weld, ties


def ring_tab(body, d=RING_D, wall=RING_WALL, side="left"):
    """(body with a tab on it, the hole to cut through it).

    The tab is a disc overlapping the end of the word by a millimetre, so the
    union is a real overlap rather than a kiss -- two shapes that touch at a
    point are one polygon whose boundary crosses itself, and that does not
    extrude to a closed solid.
    """
    x0, y0, x1, y1 = body.bounds
    r = d / 2.0 + wall
    cy = (y0 + y1) / 2.0
    cx = (x0 - r + 1.0) if side == "left" else (x1 + r - 1.0)
    disc = Point(cx, cy).buffer(r, quad_segs=32)
    hole = Point(cx, cy).buffer(d / 2.0, quad_segs=32)
    # The disc is placed against the bounding box, and a letter need not have
    # any ink there -- a T has nothing at half height but its stem, so a tab
    # tucked under its arm touches air.  Run the neck to the nearest actual
    # ink rather than to where the box says the letter starts.
    joined = unary_union([body, disc])
    if joined.geom_type == "MultiPolygon":
        # From the middle of the disc, not from its rim: the rim may already be
        # touching the letter at a point, and a neck of no length buffers to
        # nothing at all.  Round caps, so even a short one has a body.
        middle = Point(cx, cy)
        reach = nearest_points(middle, body)[1]
        neck = LineString([middle, reach]).buffer(wall / 2.0, cap_style=1, quad_segs=8)
        joined = unary_union([body, disc, neck])
    return fill_cracks(joined), hole


def counters(poly):
    """The holes in the welded word, as areas -- the a, e and o.  A counter
    that has closed up is not in here at all, which is the point of measuring
    the smallest one that is left."""
    rings = list(poly.interiors) if poly.geom_type == "Polygon" else [
        r for g in poly.geoms for r in g.interiors]
    return [cards.Polygon(r) for r in rings]


def build(text="", font=None, cap=CAP, thick=THICK, rise=RISE, weld=WELD,
          gap=GAP, bridge=BRIDGE, ring=True, ring_d=RING_D, hole_side="left",
          colours=cards.COLOURS, label="", outline=True):
    """One name keyring, as printable parts plus the numbers worth knowing.

    Returns ([part], info) in cards.build()'s shape: one part, its groups
    filed by colour slot and by field, and a welded mesh for the STL.

    `outline` False drops the raised letters and leaves the welded word as one
    flat solid -- the single-colour version, where the weld is all you see.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("a name keyring needs a name")
    font = font or cards.default_font()
    colours = tuple(colours or cards.COLOURS)
    rise = max(0.0, float(rise))

    shapes = glyphs(text, font, cap, gap)
    body_2d, weld_used, ties = weld_together(shapes, weld, bridge)
    hole = None
    if ring:
        body_2d, hole = ring_tab(body_2d, ring_d, RING_WALL, hole_side)

    # Centre it on the origin, letters and body together, so it lands on the
    # plate like everything else here.
    x0, y0, x1, y1 = body_2d.bounds
    dx, dy = -(x0 + x1) / 2.0, -(y0 + y1) / 2.0
    move = lambda p: affinity.translate(p, dx, dy)
    body_2d = move(body_2d)
    shapes = [move(s) for s in shapes]
    if hole is not None:
        hole = move(hole)

    plate = cards.prisms([body_2d], 0.0, thick)[0]
    if hole is not None:
        plate = cards.boolean("difference", [plate, *cards.prisms([hole], -1.0, thick + 2.0)])

    groups = [dict(slot="body", element="body", face="front", mesh=plate)]
    if outline and rise > 0:
        letters = cards.union(cards.prisms(shapes, thick - 0.01, rise + 0.01))
        groups.append(dict(slot="primary", element="name", face="front", mesh=letters))

    # The label is what the 3MF calls its objects, so a keyring on its own
    # gets its own name rather than the generic one.
    part = dict(name="", label=label or text, card=0, groups=groups,
                assembled=np.eye(4))
    part["slots"] = cards.slot_meshes(part)
    solids = [part["slots"][s] for s in cards.SLOTS if s in part["slots"]]
    part["mesh"] = solids[0] if len(solids) == 1 else cards.boolean("union", solids)
    parts = [part]

    holes = counters(body_2d)
    smallest = min((cards.stroke_width(h) for h in holes), default=0.0)
    lo, hi = body_2d.bounds[:2], body_2d.bounds[2:]
    stroke = cards.narrowest([body_2d] if body_2d.geom_type == "Polygon"
                             else list(body_2d.geoms))
    info = dict(
        kind="name", label=label, text=text,
        # The letters are on top, not face down like a card's: this one is
        # read from +Z, which is also how it prints.
        front_up=True,
        w=round(hi[0] - lo[0], 2), h=round(hi[1] - lo[1], 2),
        thick=thick, rise=rise, face=cards.FACE, chamfer=0.0,
        cap=round(cap, 2), weld=round(weld_used, 2), bridges=ties,
        ring=bool(ring), ring_d=ring_d if ring else None,
        counters=len(holes), counter=round(float(smallest), 2) if holes else None,
        layout=None, look=None, pattern_stroke=None,
        slots=sorted({g["slot"] for g in groups}, key=cards.SLOTS.index),
        part_slots={"name": sorted({g["slot"] for g in groups}, key=cards.SLOTS.index)},
        parts=["name"], pins=0,
        part_thick=round(thick + rise, 2), assembled=round(thick + rise, 2),
        pocket=[0.0, 0.0, 0.0], tag_mode="none", joint=None, tag=[0, 0, 0],
        lines={"name": cards.measure(shapes, cap, text)},
        logo=None, qr=None, nozzle=None,
        mark_stroke=0.0, tap_stroke=None, pause_z=None,
        volume=round(part["mesh"].volume / 1000.0, 2),
        watertight=part["mesh"].is_watertight and part["mesh"].is_winding_consistent,
        font=cards.Path(font).name,
    )
    info["total_z"] = round(float(part["mesh"].bounds[1][2]), 2)
    info["colour_z"] = round(thick + rise, 2) if rise else round(thick, 2)
    # Printed flat on its back, the body is the first `thick` mm and the
    # letters everything above: one filament change, at the top of the body.
    info["colour_bands"] = [[0.0, round(thick, 2)],
                            [round(thick, 2), info["total_z"]]] if rise else \
                           [[0.0, round(thick, 2)]]
    info["thin"] = ["outline"] if stroke < cards.MIN_STROKE else []
    if holes and smallest < MIN_COUNTER:
        info["thin"].append("counters")
    return parts, info


def build_batch(rows, **kw):
    """One keyring per row, labelled by name; one list, one plate."""
    parts, infos = [], []
    for i, row in enumerate(rows):
        p, info = build(row["name"], label=row["name"], **kw)
        for part in p:
            part["card"] = i
        parts += p
        infos.append(info)
    return parts, infos
