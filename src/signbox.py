"""A sign enclosure: a shallow box with the name lit through its own face.

    parts, info = signbox.build("OPEN", w=140, h=60)
    parts, info = signbox.build(svg=open("arrow.svg").read(), depth=30)

Two parts -- a case and a lid that drops into the back of it -- with an LED
strip stuck inside and a cable out of the bottom.  What makes it a sign rather
than a box is the front face, which is three things stacked in the first two
millimetres of the print:

  1. an **opaque layer**, OPAQUE mm of it, with the letters taken clean out;
  2. the **letters** themselves, filled back in in a translucent filament,
     flush with the opaque layer -- the same inlay a card's lettering is;
  3. a **diffuser**, a translucent sheet DIFFUSE mm thick covering the whole
     inside of the face, which is what turns four hot points of LED into an
     evenly lit word.

Printed face down, that is the bottom eight to sixteen layers: the colour
changes all happen there and the rest of the part is one filament.

The diffuser is not only there for the light.  Cut an O out of an opaque face
and the middle of the O is an island -- the [stencil](stencil.py) problem, and
the reason that one needs bridges.  Here the sheet behind the face is printed
straight over every island and welds it on, so the counters stay where the type
designer put them and there is nothing to bridge.  Set the diffuser to 0 and
that goes away with it, which is why 0 is refused rather than allowed.

The parts are the same shape as cards.build()'s, so the plate layout, the 3MF,
the STL and the app's viewer all take them unchanged.
"""
import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import box as box_2d
from shapely.ops import unary_union

import cards
import stencil
import typefaces

# The face.  120 x 60 is a name over a doorway or along the back of a desk,
# and it is the stencil's plate on purpose: the two share their sliders in the
# app, and a size that suits one suits the other.
W = 120.0
H = 60.0

# How deep the box is, front face to back.  Light off a strip stuck to the lid
# needs room to spread before it reaches the diffuser, and about 20 mm of it is
# where a single row of LEDs stops reading as a row of LEDs.
DEPTH = 24.0

# Walls.  2 mm is five lines of a 0.4 mm nozzle -- stiff enough to hold the
# lid's friction fit without bowing, and opaque enough that the light comes out
# of the letters rather than the sides.
WALL = 2.0

# The two layers of the front face.  The opaque one is what the letters are cut
# out of, so it is also what stops the light everywhere else: under 0.8 mm a
# white-ish filament glows all over and the word stops standing out.
OPAQUE = 0.8
DIFFUSE = 0.8

# Plastic left round the lettering.  It is measured from the outside edge, so
# it has to clear the wall as well: anything less than the wall plus a little
# would put the cut into the wall itself, where there is no diffuser behind it
# to hold it together or to light it.
MARGIN = 10.0
EDGE = 1.0

# A square corner on a box this size looks like a package.  5 mm rounds it.
RADIUS = 5.0

# A 45-degree break on the front outer edge, which is the edge you see.
CHAMFER = 0.8

# The lid: a plate that drops into a rebate in the back of the walls and stops
# on the ledge that leaves, flush with the back edge.  It is a friction fit --
# CLEARANCE all round -- because a printed snap this size is a thing that
# breaks off in the hand, and because a lid you can get back off is what lets
# you replace the strip.  Tight to get on: open it up with more clearance.
LID = 2.0
CLEARANCE = 0.2

# The notch the cable leaves by: cut into the back edge of the bottom wall, so
# it is open to the outside and prints without bridging anything.  The lid
# takes up the top LID mm of it, so the notch is cut that much deeper and the
# cable still gets its full CABLE mm.  0 leaves the wall closed.
CABLE = 6.0

# Clear air between the diffuser and the lid the strip is stuck to.  Less than
# this and you can count the LEDs through the letters.
MIN_CLEAR = 12.0

# A letter narrower than this comes out as a smear of translucent filament
# rather than a lit stroke, which is the same number a card's lettering wants
# and for a related reason.
MIN_STROKE = cards.MIN_STROKE


def shell(w, h, radius, outer, inner, depth, front, chamfer):
    """The case: a closed front, four walls, and nothing at the back.

    The chamfer is on the front outer edge only -- the edge that is seen.  The
    back edge stays square, because it is what the lid's rebate is cut into.
    It is a true loft, the way a card's edge is: `rounded_rect()` and the same
    rectangle inset by the chamfer are built the same way, so they correspond
    vertex for vertex and skin cleanly.
    """
    c = min(chamfer, radius - 0.2, front / 2.0)
    if c <= 0.05:
        body = cards.prisms([outer], 0.0, depth)[0]
    else:
        lip = cards.rounded_rect(w - 2 * c, h - 2 * c, radius - c)
        body = cards.boolean("union", [
            cards.loft(lip, 0.0, outer, c),
            *cards.prisms([outer], c - 0.01, depth - c + 0.01),
        ])
    return cards.boolean("difference",
                         [body, *cards.prisms([inner], front, depth - front + 1.0)])


def build(text="", svg=None, font=None, w=W, h=H, depth=DEPTH, wall=WALL,
          diffuse=DIFFUSE, opaque=OPAQUE, margin=MARGIN, radius=RADIUS,
          chamfer=CHAMFER, lid=True, lid_thick=LID, clearance=CLEARANCE,
          cable=CABLE, colours=cards.COLOURS, label=""):
    """One sign enclosure, as printable parts plus the numbers worth knowing.

    Returns ([case, lid], info) in cards.build()'s shape -- or ([case], info)
    with `lid` False, which is the open-backed version for a sign that is going
    to be screwed to something anyway.

    `svg` wins over `text` when both are given: the artwork is the artwork, and
    it is lit exactly the way the lettering is.  `font` is a face from
    typefaces.FACES or the path to a TTF; a heavy face lights better than a
    fine one, because what is lit is the stroke.
    """
    w, h, depth = float(w), float(h), float(depth)
    wall = max(0.8, float(wall))
    diffuse, opaque = float(diffuse), max(0.4, float(opaque))
    if diffuse < 0.2:
        raise ValueError("the diffuser is what holds the middle of an O in and "
                         "what spreads the light -- it cannot be 0")
    front = opaque + diffuse
    lid_thick = max(0.8, float(lid_thick)) if lid else 0.0
    radius = max(0.0, min(float(radius), w / 2.0, h / 2.0))
    margin = max(float(margin), wall + EDGE)
    cable = max(0.0, float(cable))
    colours = tuple(colours or cards.COLOURS)

    if depth <= front + lid_thick + 2.0:
        raise ValueError(f"a {depth:g} mm box has no room inside it for a strip: the "
                         f"face and the lid already take {front + lid_thick:.1f} mm")
    box_w, box_h = w - 2.0 * margin, h - 2.0 * margin
    if box_w <= 1.0 or box_h <= 1.0:
        raise ValueError(f"a {w:g} x {h:g} mm face has no room left inside a "
                         f"{margin:g} mm margin")

    outer = cards.rounded_rect(w, h, radius)
    inner = outer.buffer(-wall)                  # the cavity, and the lit area
    if inner.is_empty or inner.geom_type != "Polygon":
        raise ValueError(f"a {wall:g} mm wall leaves nothing inside a "
                         f"{w:g} x {h:g} mm box")
    room = outer.buffer(-margin)

    face = typefaces.face(font)
    if svg:
        shapes, _, _ = stencil.art_svg(svg, box_w, box_h)
        cap = 0.0
    else:
        text = (text or "").strip()
        if not text:
            raise ValueError("a sign needs some words, or an SVG")
        shapes, _, _, cap = stencil.art_text(text, face["path"], box_w, box_h)
    # Fitting to the inner rectangle is not quite enough on a rounded face:
    # a word set corner to corner crosses the arc.  Same problem the stencil
    # has, same answer.
    shapes = stencil.tuck(shapes, room)
    # The face is printed face down, so what is built in these coordinates is
    # mirrored by the time you are looking at the lit side of it: the artwork
    # goes in backwards, exactly as a card's front does.
    shapes = [affinity.scale(p, -1.0, 1.0, origin=(0, 0)) for p in shapes]
    letters = stencil.pieces(unary_union(shapes))

    # The lid's rebate: the last lid_thick mm of the wall is taken back to its
    # outer half, and the step that leaves is what the lid sits on.
    rebate = inner.buffer(wall / 2.0)
    cuts = []
    if lid:
        cuts += cards.prisms([rebate], depth - lid_thick, lid_thick + 1.0)
    if cable > 0:
        if cable > inner.bounds[2] - inner.bounds[0]:
            raise ValueError(f"a {cable:g} mm cable notch is wider than the wall it "
                             f"goes through")
        # Open to the back and open to the outside: no bridge, no support, and
        # the cable drops in rather than being threaded.
        notch = box_2d(-cable / 2.0, -h / 2.0 - 1.0, cable / 2.0, -h / 2.0 + wall + 1.0)
        cuts += cards.prisms([notch], depth - lid_thick - cable, lid_thick + cable + 1.0)

    # The face: the letters taken out of the opaque layer, and the diffuser
    # slot taken out of the whole of the inside of it.  Both are filled back in
    # below, each overlapping the body by a hundredth of a millimetre so the
    # welded STL has something to bite on.
    cuts += cards.prisms(letters, -1.0, 1.0 + front)
    cuts += cards.prisms([inner], front - diffuse, diffuse)
    case = cards.boolean("difference",
                         [shell(w, h, radius, outer, inner, depth, front, chamfer), *cuts])

    lit = trimesh.util.concatenate(cards.prisms(letters, 0.0, front))
    sheet = cards.prisms([inner], front - diffuse - 0.01, diffuse + 0.01)[0]
    parts = [dict(name="case", groups=[
        dict(slot="body", element="body", face="body", mesh=case),
        dict(slot="primary", element="name", face="front", mesh=lit),
        dict(slot="primary", element="diffuser", face="front", mesh=sheet),
    ], assembled=np.eye(4))]

    if lid:
        # Not notched for the cable: the notch is cut a cable's width deeper
        # than the lid, so the cable passes under a lid that stays whole --
        # which is what holds the cable in and keeps the light off the wall.
        plate = cards.prisms([rebate.buffer(-clearance)], 0.0, lid_thick)[0]
        # Printed inside face down, which is the side the strip is stuck to:
        # the plate side of a print is the flat one, and a strip's adhesive
        # wants a flat one.  No turn, so the move back into the box is a lift.
        parts.append(dict(name="lid", groups=[
            dict(slot="body", element="lid", face="back", mesh=plate)],
            assembled=trimesh.transformations.translation_matrix(
                (0.0, 0.0, depth - lid_thick))))

    for part in parts:
        part["label"] = label or (text or "sign")
        part["card"] = 0
        part["slots"] = cards.slot_meshes(part)
        solids = [part["slots"][s] for s in cards.SLOTS if s in part["slots"]]
        part["mesh"] = solids[0] if len(solids) == 1 else cards.boolean("union", solids)

    stroke = cards.narrowest(letters)
    clear = depth - front - lid_thick
    x0, y0, x1, y1 = cards.extent(shapes)
    info = dict(
        kind="sign", label=label, text="" if svg else text,
        # The face is laid out face down, the way a card is: the side you read
        # points at the build plate.
        front_up=False,
        w=round(w, 2), h=round(h, 2), thick=round(depth, 2), rise=0.0,
        depth=round(depth, 2), wall=round(wall, 2), front=round(front, 2),
        opaque=round(opaque, 2), diffuse=round(diffuse, 2), clear=round(clear, 2),
        lid=bool(lid), lid_thick=round(lid_thick, 2) if lid else None,
        clearance=round(clearance, 2) if lid else None,
        cable=round(cable, 2) if cable else None,
        margin=round(margin, 2), radius=round(radius, 2),
        face=cards.FACE, chamfer=round(chamfer, 2),
        cap=round(cap, 2), art=[round(float(x1 - x0), 2), round(float(y1 - y0), 2)],
        letters=len(letters), stroke=round(float(stroke), 2),
        lit_area=round(100.0 * unary_union(letters).area / inner.area, 1),
        nozzle=cards.nozzle_for(stroke),
        svg=bool(svg), font=cards.Path(face["path"]).name,
        typeface=face["key"], typeface_name=face["font"], min_cap=None,
        layout=None, look=None, pattern_stroke=None,
        slots=sorted({g["slot"] for p in parts for g in p["groups"]},
                     key=cards.SLOTS.index),
        part_slots={p["name"]: sorted(p["slots"], key=cards.SLOTS.index) for p in parts},
        parts=[p["name"] for p in parts], pins=0,
        part_thick=round(max(front, lid_thick), 2), assembled=round(depth, 2),
        pocket=[0.0, 0.0, 0.0], tag_mode="none", joint=None, tag=[0, 0, 0],
        lines={} if svg else {"sign": cards.measure(shapes, cap, text)},
        logo=None, qr=None, mark_stroke=0.0, tap_stroke=None, pause_z=None,
        volume=round(sum(p["mesh"].volume for p in parts) / 1000.0, 2),
        watertight=all(p["mesh"].is_watertight and p["mesh"].is_winding_consistent
                       for p in parts),
    )
    info["total_z"] = round(float(max(p["mesh"].bounds[1][2] for p in parts)), 2)
    # Face down, every colour is in the front face and the rest of the case is
    # one filament: one change on the way in, one on the way out.
    info["colour_z"] = round(front, 2)
    info["colour_bands"] = [[0.0, round(front, 2)]]
    info["thin"] = ([] if stroke >= MIN_STROKE else ["the letters"]) + \
                   ([] if opaque >= 0.6 else ["the opaque layer"]) + \
                   ([] if wall >= 1.2 else ["the walls"])
    info["dim"] = clear < MIN_CLEAR
    return parts, info


def build_batch(rows, **kw):
    """One sign per row, labelled by what it says; one list, one plate."""
    parts, infos = [], []
    for i, row in enumerate(rows):
        p, info = build(row["name"], label=row["name"], **kw)
        for part in p:
            part["card"] = i
        parts += p
        infos.append(info)
    return parts, infos
