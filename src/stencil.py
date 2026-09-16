"""A stencil: a rectangle with the shape cut clean through it.

    parts, info = stencil.build("SHOP", w=120, h=60)
    parts, info = stencil.build(svg=open("arrow.svg").read(), w=90, h=90)

The problem here is the name keyring's, backwards.  A keyring has to make one
solid out of the several a word is; a stencil has to keep one plate in one
piece while taking that same word *out* of it.  Cut an O through a plate and
the middle of the O is a loose disc: it drops out on the print bed, or it
prints attached to nothing and comes off in the bag.  The counter of an A, the
eye of an e, the middle of any ring in an SVG -- every one of them is an
island the moment the cut goes through.

So each island is found and tied back to the plate with a **bridge**: a bar of
plate left uncut across the shortest crossing between the island and whatever
is already anchored.  It is the little interruption in every road-marking and
mailbox stencil, and it is not a flaw in them -- it is the only reason the
letters still have middles.  Nesting comes out on its own: the largest loose
piece is tied first, and once it is anchored it can hold the next one in.

What you paint through is the cut; what you hold is the frame round it.  Both
are measured and reported, because a cut narrower than a nozzle will not print
open however carefully you draw it, and a frame narrower than a few lines will
not survive being peeled off a wet wall.

The parts are the same shape as cards.build()'s, so the plate layout, the 3MF,
the STL and the app's viewer all take them unchanged.
"""
import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString
from shapely.ops import nearest_points, unary_union

import cards
import trace_svg
import typefaces

# The plate.  120 x 60 is a two-word sign or a one-word label, and about as
# much as a hand holds flat against a wall.
W = 120.0
H = 60.0

# Thin, on purpose.  A stencil wants to sit flat on the surface -- every
# millimetre of thickness is a millimetre of wall the paint has to reach round,
# which is what makes a fuzzy edge -- and 0.8 mm is four layers at 0.2 and
# still stiff enough to peel off in one piece.
THICK = 0.8

# The frame left round the cut.  It is what you hold and what stops overspray,
# so it is generous by default; 0 puts the artwork hard against the edge.
MARGIN = 8.0

# A square corner on a thin plate is a thing that catches and tears.
RADIUS = 4.0

# The least plate there can ever be between the cut and the outside edge.  It
# is not a taste thing: artwork laid exactly on the edge meets it at a point,
# and a polygon whose boundary touches itself does not extrude to a closed
# solid -- the plate would come out as a mesh with a pinhole in it rather than
# as a stencil.  Ask for a 0 margin and this is what you get, and the readout
# then says the plate is thinner than it can print, which it is.

# The bar left across each island.  1.6 mm is four lines of a 0.4 mm nozzle:
# thin enough to read as an interruption rather than a stroke, thick enough to
# survive being washed and peeled.  0 leaves the islands loose, which is what
# you want only if you are placing them by hand.
EDGE = 0.2

BRIDGE = 1.6
BRIDGE_MAX = 64          # a runaway loop would be a bug, not a stencil

# A cut this narrow stops being a cut: the slicer bridges it, and paint will
# not go through what it does leave.  Reported, not refused -- the answer is
# bigger artwork or a heavier face, and that is the user's call.
MIN_CUT = 0.8

# Plate this narrow will not survive handling, whether it is a bridge, the
# frame, or the ligature the cut left between two letters.
MIN_WEB = 0.8


def fit(polys, box_w, box_h):
    """The shapes scaled to fill the box and centred in it, by their ink.

    By the ink, not by the em or the cap height: the margin is a promise about
    how much plate is left round the cut, and a capital O overshoots its own
    cap height by a whisker in most faces -- enough, on a narrow margin, to put
    the cut through the edge of the plate.
    """
    x0, y0, x1, y1 = cards.extent(polys)
    k = min(box_w / (x1 - x0), box_h / (y1 - y0))
    cx, cy = (x0 + x1) / 2.0 * k, (y0 + y1) / 2.0 * k
    out = [affinity.translate(affinity.scale(p, k, k, origin=(0, 0)), -cx, -cy)
           for p in polys]
    return out, (x1 - x0) * k, (y1 - y0) * k, k


def tuck(polys, room, steps=12):
    """The shapes shrunk, if they have to be, until they sit inside `room`.

    Fitting to the inner rectangle is not quite enough on a plate with rounded
    corners: a word set corner to corner crosses the arc and the cut runs out
    through the edge.  Two per cent a pass is finer than any margin anybody
    types, and on the usual stencil the first test passes and nothing happens.
    """
    # A hair of slack: the fit puts the ink exactly on the box edge, and a
    # float's worth of overshoot there is not a reason to shrink the artwork.
    room = room.buffer(1e-6)
    for _ in range(steps):
        if unary_union(polys).within(room):
            break
        polys = [affinity.scale(p, 0.98, 0.98, origin=(0, 0)) for p in polys]
    return polys


def art_text(text, font, box_w, box_h):
    """The lettering, set as large as the box will take it.

    `|` or a newline splits lines, which is cards.text_block's rule and the
    reason a two-word stencil does not have to be one long thin word.
    """
    polys, _, _, cap = cards.text_block(text, font, box_h, box_w)
    if not polys:
        raise ValueError("nothing to cut: give it some words")
    polys, w, h, k = fit(polys, box_w, box_h)
    return polys, w, h, cap * k


def art_svg(svg, box_w, box_h):
    """The SVG's filled geometry, scaled to the box and centred on it.

    Every fill is one cut -- a stencil has no colours to sort them into, and
    two overlapping paths mean one hole.
    """
    shapes = trace_svg.shapes(svg)
    if not shapes:
        raise ValueError("nothing in that SVG to cut -- flat fills only, and "
                         "text has to be outlines")
    polys, w, h, _ = fit(shapes, box_w, box_h)
    return polys, w, h


def pieces(poly):
    return list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]


def solid(body_2d, plate_2d, cut, thick):
    """The cut plate, `thick` mm deep, as one closed mesh.

    The direct way is to extrude the cut plate, and on a word set in an
    ordinary face that is what happens here.  It is not reliable on every
    plate, though: the triangulator has to cut a face with holes in it down to
    one ring, and it does that by running a seam out to the outline from each
    hole, so with enough holes two seams land on the same vertex and the mesh
    comes back open.  It is a coincidence rather than a limit -- twenty-six
    holes come out closed and ten do not -- but the odds of it go up with
    every hole, and a face drawn as a stencil is nothing but holes: SHOP is
    nine cuts in Saira Stencil One and ten in Stardos Stencil, against four in
    the sans, and the Stardos one is among the plates that fail.

    So when the extrusion does not close, the same plate is built the other
    way round: a whole rectangle with the cut punched out of it by the boolean
    engine, which triangulates none of it and cannot leave that seam.  The
    punches are deliberately taller than the plate and start below it, because
    two faces in the same plane are the one thing a boolean is bad at.
    """
    try:
        solids = cards.prisms(pieces(body_2d), 0.0, thick)
        return solids[0] if len(solids) == 1 else trimesh.util.concatenate(solids)
    except ValueError:
        plate = cards.prisms([plate_2d], 0.0, thick)[0]
        return cards.boolean("difference",
                             [plate] + cards.prisms(pieces(cut), -thick, 3.0 * thick))


def web(holes, plate, most=99.0):
    """The narrowest bar of plate the cut leaves, in mm.

    Plate is thin in exactly two places: between two cuts that came close --
    the gap between the L and the A of a word set tight -- and between a cut
    and the outside edge.  Both are gaps rather than shapes, so both are
    measured as distances rather than by any stroke-width rule of thumb, and
    the smaller of them is what will tear.  The bridges are not in here: their
    width is set rather than discovered, and `bridge` reports it.
    """
    gaps = [a.distance(b) for i, a in enumerate(holes) for b in holes[i + 1:]]
    gaps += [plate.exterior.distance(h) for h in holes]
    return round(min(gaps, default=most), 2)


def islands(plate, cut):
    """(the anchored plate, the pieces that are not): what the cut has cut off.

    A piece is anchored if it still reaches the outside edge of the plate.
    Everything else is an island, whatever its size -- the middle of an O is
    an island, and so is a whole letter sitting inside the bowl of another.
    """
    material = plate.difference(cut)
    pieces = list(material.geoms) if material.geom_type == "MultiPolygon" else [material]
    edge = plate.exterior
    held = [g for g in pieces if edge.distance(g) < 1e-9]
    loose = [g for g in pieces if edge.distance(g) >= 1e-9]
    return unary_union(held) if held else None, loose


def bridge_islands(plate, cut, width=BRIDGE):
    """(the cut with bridges taken out of it, how many it took).

    Largest island first, each tied across the shortest line between it and
    the anchored plate.  Round caps, so the bar has real overlap at both ends
    rather than meeting the island at a point -- two shapes that touch at a
    point are one polygon whose boundary crosses itself, and that does not
    extrude to a closed solid.
    """
    ties = 0
    while ties < BRIDGE_MAX:
        held, loose = islands(plate, cut)
        if held is None or not loose:
            break
        island = max(loose, key=lambda g: g.area)
        a, b = nearest_points(island, held)
        bar = LineString([a, b]).buffer(width / 2.0, cap_style=1, quad_segs=8)
        cut = cut.difference(bar)
        ties += 1
    return cut, ties


def build(text="", svg=None, font=None, w=W, h=H, thick=THICK, margin=MARGIN,
          radius=RADIUS, bridge=BRIDGE, colours=cards.COLOURS, label=""):
    """One stencil, as printable parts plus the numbers worth knowing.

    Returns ([part], info) in cards.build()'s shape: one part, one colour,
    and a plate with the artwork cut through it.

    `margin` is the plate left round the cut; it never goes below EDGE, or the
    cut would meet the outside edge at a point and the plate would not close.

    `svg` wins over `text` when both are given -- the artwork is the artwork.
    `font` is a face from typefaces.FACES or the path to a TTF; the heavier
    the face, the wider the cut and the fewer the bridges.
    """
    w, h = float(w), float(h)
    thick = max(0.2, float(thick))
    margin = max(0.0, float(margin))
    radius = max(0.0, min(float(radius), w / 2.0, h / 2.0))
    margin = max(margin, EDGE)          # what is asked for, or what will close
    box_w, box_h = w - 2.0 * margin, h - 2.0 * margin
    if box_w <= 1.0 or box_h <= 1.0:
        raise ValueError(f"a {w:g} x {h:g} mm plate has no room left inside a "
                         f"{margin:g} mm margin")

    plate_2d = cards.rounded_rect(w, h, radius)
    room = plate_2d.buffer(-margin)
    if room.is_empty:
        raise ValueError(f"a {margin:g} mm margin leaves nothing of a "
                         f"{w:g} x {h:g} mm plate")

    face = typefaces.face(font)
    if svg:
        shapes, art_w, art_h = art_svg(svg, box_w, box_h)
        cap = 0.0
    else:
        text = (text or "").strip()
        if not text:
            raise ValueError("a stencil needs some words, or an SVG")
        shapes, art_w, art_h, cap = art_text(text, face["path"], box_w, box_h)

    shapes = tuck(shapes, room)
    cut = unary_union(shapes)
    ties = 0
    if bridge > 0:
        cut, ties = bridge_islands(plate_2d, cut, float(bridge))
    body_2d = plate_2d.difference(cut)

    # Bridged, the plate is one solid; with the bridges turned off it is the
    # frame and a little pile of loose islands, which is a legitimate thing to
    # ask for and prints as several bodies on one plate.
    groups = [dict(slot="body", element="body", face="front",
                   mesh=solid(body_2d, plate_2d, cut, thick))]
    part = dict(name="", label=label or (text or "stencil"), card=0, groups=groups,
                assembled=np.eye(4))
    part["slots"] = cards.slot_meshes(part)
    part["mesh"] = part["slots"]["body"]
    parts = [part]

    # What you paint through, and what you hold: both are measured, because a
    # cut under a nozzle will not open and a web under one will not last.
    holes = pieces(cut)
    finest_cut = cards.narrowest(holes)
    finest_web = web(holes, plate_2d)
    _, still_loose = islands(plate_2d, cut)

    x0, y0, x1, y1 = cards.extent(shapes)
    info = dict(
        kind="stencil", label=label, text="" if svg else text,
        front_up=True,
        w=round(w, 2), h=round(h, 2), thick=round(thick, 2), rise=0.0,
        face=cards.FACE, chamfer=0.0,
        margin=round(margin, 2), radius=round(radius, 2),
        cap=round(cap, 2), art=[round(float(x1 - x0), 2), round(float(y1 - y0), 2)],
        bridge=round(float(bridge), 2), bridges=ties, loose=len(still_loose),
        cut=round(float(finest_cut), 2), web=round(float(finest_web), 2),
        open_area=round(100.0 * cut.area / plate_2d.area, 1),
        nozzle=cards.nozzle_for(finest_cut),
        svg=bool(svg), font=cards.Path(face["path"]).name,
        typeface=face["key"], typeface_name=face["font"], min_cap=None,
        layout=None, look=None, pattern_stroke=None,
        slots=["body"], part_slots={"stencil": ["body"]}, parts=["stencil"], pins=0,
        part_thick=round(thick, 2), assembled=round(thick, 2),
        pocket=[0.0, 0.0, 0.0], tag_mode="none", joint=None, tag=[0, 0, 0],
        lines={} if svg else {"stencil": cards.measure(shapes, cap, text)},
        logo=None, qr=None, mark_stroke=0.0, tap_stroke=None, pause_z=None,
        holes=len(holes),
        volume=round(part["mesh"].volume / 1000.0, 2),
        watertight=part["mesh"].is_watertight and part["mesh"].is_winding_consistent,
    )
    info["total_z"] = round(float(part["mesh"].bounds[1][2]), 2)
    info["colour_z"] = round(thick, 2)
    info["colour_bands"] = [[0.0, round(thick, 2)]]
    info["thin"] = ([] if finest_cut >= MIN_CUT else ["the cut"]) + \
                   ([] if finest_web >= MIN_WEB else ["the plate"])
    return parts, info


def build_batch(rows, **kw):
    """One stencil per row, labelled by name; one list, one plate."""
    parts, infos = [], []
    for i, row in enumerate(rows):
        p, info = build(row["name"], label=row["name"], **kw)
        for part in p:
            part["card"] = i
        parts += p
        infos.append(info)
    return parts, infos
