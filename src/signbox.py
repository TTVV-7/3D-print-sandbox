"""A sign enclosure: a shallow box with the name lit through its own face.

    parts, info = signbox.build("Name")                  # the box is the word
    parts, info = signbox.build("OPEN", shape="box")     # a plain rectangle
    parts, info = signbox.build(svg=open("logo.svg").read())

Two parts -- a case and a lid that drops into the back of it -- with an LED
strip stuck inside and the lead out of a hole in the back.  What makes it a
sign rather than a box is the front face, which is three things stacked in the
first two millimetres of the print:

  1. an **opaque layer**, OPAQUE mm of it, with the lit shapes taken clean out;
  2. those shapes, filled back in in a translucent filament, flush with the
     opaque layer -- the same inlay a card's lettering is;
  3. a **diffuser**, a translucent sheet DIFFUSE mm thick covering the whole
     inside of the face, which is what turns four hot points of LED into an
     even glow.

Printed face down, that is the bottom eight to sixteen layers: the colour
changes all happen there and the rest of the part is one filament.

What is lit depends on the outline, and the two are opposites:

  letters - the case **is the word**: the outline is the lettering grown
            outward by `border`, so the box is a fat rounded copy of the word
            itself.  What lights up is the band between the letters and that
            outline -- the letter faces stay opaque and the glow runs round
            them, which is the shop-sign look, and the counters of the a and
            the e come out as lit pockets, because growing a letter outward
            closes its small holes.
  box     - a rectangle with the letters themselves lit through it: the plain
            light box.

The diffuser is not only there for the light.  Cut a shape out of an opaque
face and whatever it encloses is an island -- the [stencil](stencil.py)
problem, and the reason that one needs bridges.  Here the sheet behind the
face is printed straight over every island and welds it on: the middle of an O
in box mode, every letter face in letters mode.  So there is nothing to bridge
in the face at all, and setting the diffuser to 0 is refused rather than
allowed.

The parts are the same shape as cards.build()'s, so the plate layout, the 3MF,
the STL and the app's viewer all take them unchanged.
"""
import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points, unary_union

import cards
import nametag
import stencil
import trace_svg
import typefaces

# The two outlines.  The word's own shape is the default because it is what
# people mean by a name light: a rectangle with a word in it is a light box,
# and the word cut out of its own fat copy is a sign.
SHAPES = ("letters", "box")
SHAPE = "letters"

# Letters mode: how tall the capitals are, and how far the case stands off
# them.  40 mm is a name across a desk or over a door; the border is what
# glows, so it is generous -- 8 mm of it, less the 2 mm wall, leaves a 6 mm
# band of light round every stroke.
CAP = 40.0
BORDER = 8.0

# How far the outline may be moved to drop a point from it.  A buffer of a
# traced script arrives with a thousand points in it, nearly all of them on
# arcs a fifth of a nozzle long, and every one is paid for five times over --
# the wall, the cavity, the rebate, the chamfer's insets and the lid all carry
# the same outline.  A twentieth of a millimetre is under a tenth of a 0.4 mm
# extrusion and takes it to about two hundred points.
SMOOTH = 0.05

# Two lines, and how far apart they sit.  Far enough that the ink of one
# clears the ink of the other, near enough that their borders overlap and the
# sign is one piece rather than two tied together by a bridge -- which is the
# tighter of the two on any border worth having, and the reason the leading
# here is a function of the border rather than a number out of a type book.
LEADING = 1.45
LEADING_MIN = 1.15

# What ties two letters together when the border alone has not.  A script
# joins up on its own and a sans at 8 mm usually does too, but "I I" at a
# tight border does not, and a sign in two pieces is not a sign.
BRIDGE = 3.0

# Box mode: the face.  120 x 60 is the stencil's plate on purpose -- the two
# share their sliders in the app, and a size that suits one suits the other.
W = 120.0
H = 60.0

# Plastic left round the lettering in box mode, measured from the outside
# edge.  As with the border it has to clear the wall: a letter out there would
# be cut into the wall itself, where there is no diffuser behind it to light
# it or to hold it on.
MARGIN = 10.0
EDGE = 1.0

# How deep the box is, front face to back.  Light off a strip stuck to the lid
# needs room to spread before it reaches the diffuser, and about 20 mm of it is
# where a single row of LEDs stops reading as a row of LEDs.
DEPTH = 24.0

# Walls.  2 mm is five lines of a 0.4 mm nozzle -- stiff enough to hold the
# lid's friction fit without bowing, and opaque enough that the light comes out
# of the face rather than the sides.
WALL = 2.0

# The two layers of the front face.  The opaque one is what the lit shapes are
# cut out of, so it is also what stops the light everywhere else: under 0.8 mm
# a white-ish filament glows all over and the sign stops having a shape.
OPAQUE = 0.8
DIFFUSE = 0.8

# A square corner on a rectangle this size looks like a package; 5 mm rounds
# it.  Letters mode has no use for it -- the outline is the word's, and its
# corners are already round because the border is grown with round joins.
RADIUS = 5.0

# A 45-degree break on the front outer edge, which is the edge you see.
CHAMFER = 0.8

# The layer height everything here assumes, and the step the letters-mode
# chamfer is cut in -- see front_edge().
LAYER = 0.2

# The lid: a plate that drops into a rebate in the back of the walls and stops
# on the ledge it leaves, flush with the back edge.  It is a friction fit --
# CLEARANCE all round -- because a printed snap this size is a thing that
# breaks off in the hand, and because a lid you can get back off is what lets
# you replace the strip.  Tight to get on: open it up with more clearance.
LID = 2.0
CLEARANCE = 0.2

# The hole the lead leaves by, in the lid -- out of the back, where a wire
# belongs, rather than out of the bottom edge, where it stands the sign off
# the shelf.  It goes as low on the back as it will fit and as near the middle
# as that row allows, so the wire runs straight down the wall behind.  0 leaves
# the lid closed, for a sign running off a battery inside it.
CABLE = 6.0
CABLE_KEEP = 1.5           # plastic left round the hole

# Clear air between the diffuser and the lid the strip is stuck to.  Less than
# this and you can count the LEDs through the face.
MIN_CLEAR = 12.0

# A lit band narrower than this comes out as a smear of translucent filament
# rather than a stroke of light, which is the same number a card's lettering
# wants and for a related reason.
MIN_STROKE = cards.MIN_STROKE


def pieces(poly):
    """The polygons of a shape that may have come back as several, each wound
    the way an extrusion wants it.

    The winding matters here and nowhere else in this repo: the face is laid
    out mirrored, and mirroring a ring reverses it.  A reversed ring extrudes
    to a solid that is inside out -- still closed, still watertight, so nothing
    complains -- and subtracting an inside-out solid removes everything it does
    *not* cover.  orient() puts every exterior back anticlockwise and every
    hole clockwise.
    """
    return [] if poly.is_empty else [orient(g) for g in stencil.pieces(poly)]


def set_at(text, svg, font, cap, border=BORDER):
    """The shapes to build the sign around, `cap` mm tall, centred on the
    origin: the word set tight the way a name keyring sets it, or the artwork
    scaled to that height.  A `|` or a newline splits it over two lines, set
    close enough that their borders will merge into one sign.

    Tight, not by the font's own advance, because the letters are about to be
    grown into one another: the spacing that makes a word one printable piece
    is the spacing a sign painter uses, and nametag.glyphs() is already that.
    """
    if svg:
        shapes = trace_svg.shapes(svg)
        if not shapes:
            raise ValueError("nothing in that SVG to light -- flat fills only, "
                             "and text has to be outlines")
        _, y0, _, y1 = cards.extent(shapes)
        k = cap / (y1 - y0)
        shapes = [affinity.scale(s, k, k, origin=(0, 0)) for s in shapes]
    else:
        rows = [ln.strip() for ln in text.replace("|", "\n").split("\n") if ln.strip()]
        if not rows:
            raise ValueError("a sign needs some words, or an SVG")
        step = max(cap * LEADING_MIN, min(cap * LEADING, cap + 1.6 * border))
        shapes = []
        for i, row in enumerate(rows):
            line = nametag.glyphs(row, font, cap)
            x0, _, x1, _ = cards.extent(line)
            shapes += [affinity.translate(g, -(x0 + x1) / 2.0, -i * step) for g in line]
    x0, y0, x1, y1 = cards.extent(shapes)
    return [affinity.translate(s, -(x0 + x1) / 2.0, -(y0 + y1) / 2.0) for s in shapes]


def silhouette(shapes, border, bridge=BRIDGE):
    """(the outline the case takes, how many bridges it took): the shapes
    grown outward by `border`, with round joins, welded into one piece.

    Round joins, because the outline is the visible edge of the sign and a
    mitre on the inside of a script's curve is a spike.  Growing outward also
    shuts the small counters -- the a, the e -- which is wanted here: a closed
    counter is a pocket of light rather than a hole through the sign.  The big
    ones stay open, and the case goes round them.
    """
    grown = unary_union([s.buffer(border, quad_segs=cards.QUAD, join_style=1)
                         for s in shapes])
    body, ties = nametag.tie_together(grown, bridge)
    return nametag.fill_cracks(body).simplify(SMOOTH), ties


def front_edge(outer, depth, chamfer, step=LAYER):
    """Letters mode's outer solid, with the front edge broken.

    cards.slab() lofts its chamfer, which wants the outline and its inset to
    correspond vertex for vertex -- true of a rounded rectangle and its inset,
    not true of an arbitrary silhouette and its buffer.  So the chamfer is cut
    here the way the printer is going to make it anyway: one inset per layer.
    That is not an approximation of the part -- a 45-degree edge at a 0.2 mm
    layer height *is* a staircase of four steps, and this is those steps.
    """
    n = int(round(max(0.0, chamfer) / step))
    solids = []
    for i in range(n):
        ring = outer.buffer(-(chamfer - i * step))
        if ring.is_empty:
            continue
        solids += cards.prisms(pieces(ring), i * step, step + 0.01)
    z0 = max(0.0, n * step - 0.01)
    solids += cards.prisms(pieces(outer), z0, depth - z0 + 0.01)
    return cards.union(solids)


def shell(w, h, radius, outer, depth, front, chamfer):
    """Box mode's outer solid: a rounded-rectangle prism with a true lofted
    chamfer on the front edge, which is cards.slab()'s edge exactly."""
    c = min(chamfer, radius - 0.2, front / 2.0)
    if c <= 0.05:
        return cards.prisms([outer], 0.0, depth)[0]
    lip = cards.rounded_rect(w - 2 * c, h - 2 * c, radius - c)
    return cards.boolean("union", [
        cards.loft(lip, 0.0, outer, c),
        *cards.prisms([outer], c - 0.01, depth - c + 0.01),
    ])


def cable_spot(plan, radius, keep=CABLE_KEEP):
    """Where the lead leaves the back: the lowest point on the lid with enough
    plastic round it, and of that row the point nearest the middle.

    Low, so the wire runs down the wall behind the sign rather than standing it
    off the shelf; near the middle, because on a word-shaped lid the lowest row
    is under one letter and the middle of it is the most plastic there is.
    Refused rather than shifted when the lid is too small for the hole asked
    for -- a hole through the wall of a light box is a light leak, not a
    grommet.
    """
    room = plan.buffer(-(radius + keep))
    if room.is_empty:
        raise ValueError(f"no room on the back for a {2 * radius:g} mm cable hole "
                         f"-- a smaller hole, or a bigger sign")
    x0, y0, x1, _ = room.bounds
    row = LineString([(x0 - 1.0, y0 + 0.25), (x1 + 1.0, y0 + 0.25)]).intersection(room)
    if row.is_empty:
        return room.representative_point()
    return nearest_points(Point(0.0, y0 + 0.25), row)[1]


def build(text="", svg=None, font=None, shape=SHAPE, cap=CAP, border=BORDER,
          bridge=BRIDGE, w=W, h=H, margin=MARGIN, radius=RADIUS, depth=DEPTH,
          wall=WALL, diffuse=DIFFUSE, opaque=OPAQUE, chamfer=CHAMFER, lid=True,
          lid_thick=LID, clearance=CLEARANCE, cable=CABLE,
          colours=cards.COLOURS, label=""):
    """One sign enclosure, as printable parts plus the numbers worth knowing.

    Returns ([case, lid], info) in cards.build()'s shape -- or ([case], info)
    with `lid` False, which is the open-backed version for a sign that is
    going to be screwed to something anyway.

    `shape` is "letters", where the case is the word grown outward by `border`
    and the glow runs round the letters, or "box", where it is a `w` x `h`
    rectangle and the letters themselves are lit.  `cap` sets the lettering in
    letters mode; in box mode the words are set as large as the margin leaves
    room for and `cap` is an output rather than an input.

    `svg` wins over `text` when both are given: the artwork is the artwork, and
    it is lit -- or outlined -- exactly the way the lettering is.  `font` is a
    face from typefaces.FACES or the path to a TTF; a heavy face outlines
    better than a fine one, because the glow is a band of constant width and a
    hairline face leaves its letters swimming in it.
    """
    if shape not in SHAPES:
        raise ValueError(f"no such outline: {shape}")
    depth = float(depth)
    wall = max(0.8, float(wall))
    diffuse, opaque = float(diffuse), max(0.4, float(opaque))
    if diffuse < 0.2:
        raise ValueError("the diffuser is what holds the letter faces on and what "
                         "spreads the light -- it cannot be 0")
    front = opaque + diffuse
    lid_thick = max(0.8, float(lid_thick)) if lid else 0.0
    cable = max(0.0, float(cable))
    colours = tuple(colours or cards.COLOURS)
    if depth <= front + lid_thick + 2.0:
        raise ValueError(f"a {depth:g} mm box has no room inside it for a strip: the "
                         f"face and the lid already take {front + lid_thick:.1f} mm")

    face = typefaces.face(font)
    text = (text or "").strip()
    if not svg and not text:
        raise ValueError("a sign needs some words, or an SVG")

    # The face is printed face down, so what is built in these coordinates is
    # mirrored by the time you are looking at the lit side of it: the artwork
    # goes in backwards, exactly as a card's front does.  It is mirrored here,
    # before anything is derived from it, so that the outline a letters-mode
    # sign takes is the outline of the word as it will be read.
    mirror = lambda p: affinity.scale(p, -1.0, 1.0, origin=(0, 0))

    ties = 0
    if shape == "letters":
        cap, border = float(cap), float(border)
        if border < wall + EDGE:
            raise ValueError(f"a {border:g} mm border does not clear a {wall:g} mm "
                             f"wall -- the light would have nowhere to come out")
        shapes = [mirror(s) for s in set_at(text, svg, face["path"], cap, border)]
        outer, ties = silhouette(shapes, border, float(bridge))
        # Centre the case, lettering and all, so it lands on the plate the way
        # everything else here does.
        x0, y0, x1, y1 = outer.bounds
        dx, dy = -(x0 + x1) / 2.0, -(y0 + y1) / 2.0
        outer = affinity.translate(outer, dx, dy)
        shapes = [affinity.translate(s, dx, dy) for s in shapes]
        w, h = round(x1 - x0, 2), round(y1 - y0, 2)
        radius, margin = 0.0, border
    else:
        w, h = float(w), float(h)
        margin = max(float(margin), wall + EDGE)
        radius = max(0.0, min(float(radius), w / 2.0, h / 2.0))
        box_w, box_h = w - 2.0 * margin, h - 2.0 * margin
        if box_w <= 1.0 or box_h <= 1.0:
            raise ValueError(f"a {w:g} x {h:g} mm face has no room left inside a "
                             f"{margin:g} mm margin")
        outer = cards.rounded_rect(w, h, radius)
        if svg:
            shapes, _, _ = stencil.art_svg(svg, box_w, box_h)
            cap = 0.0
        else:
            shapes, _, _, cap = stencil.art_text(text, face["path"], box_w, box_h)
        # Fitting to the inner rectangle is not quite enough on a rounded face:
        # a word set corner to corner crosses the arc.  Same problem the stencil
        # has, same answer.
        shapes = [mirror(s) for s in stencil.tuck(shapes, outer.buffer(-margin))]

    inner = outer.buffer(-wall)                  # the cavity, and the lit area
    if inner.is_empty:
        raise ValueError(f"a {wall:g} mm wall leaves nothing inside a "
                         f"{w:g} x {h:g} mm sign")
    # What the light comes out of: the band round the letters, or the letters.
    lit_2d = (inner.difference(unary_union(shapes)) if shape == "letters"
              else unary_union(shapes))
    lit = pieces(lit_2d)
    if not lit:
        raise ValueError("nothing left to light")

    rebate = inner.buffer(wall / 2.0)
    # The cavity: everything inside the walls, from the back of the face to
    # past the back of the box.  What is left is a face, four walls and air.
    cuts = cards.prisms(pieces(inner), front, depth - front + 1.0)
    if lid:
        cuts += cards.prisms(pieces(rebate), depth - lid_thick, lid_thick + 1.0)
    # The face: the lit shapes taken out of the opaque layer, and the diffuser
    # slot taken out of the whole of the inside of it.  Both are filled back in
    # below, the sheet overlapping the body by a hundredth of a millimetre so
    # the welded STL has something to bite on.
    cuts += cards.prisms(lit, -1.0, 1.0 + front)
    cuts += cards.prisms(pieces(inner), front - diffuse, diffuse)
    case = (front_edge(outer, depth, chamfer) if shape == "letters"
            else shell(w, h, radius, outer, depth, front, chamfer))
    case = cards.boolean("difference", [case, *cuts])

    glow = trimesh.util.concatenate(cards.prisms(lit, 0.0, front))
    sheet = trimesh.util.concatenate(
        cards.prisms(pieces(inner), front - diffuse - 0.01, diffuse + 0.01))
    parts = [dict(name="case", groups=[
        dict(slot="body", element="body", face="body", mesh=case),
        dict(slot="primary", element="name", face="front", mesh=glow),
        dict(slot="primary", element="diffuser", face="front", mesh=sheet),
    ], assembled=np.eye(4))]

    if lid:
        plan = unary_union(pieces(rebate.buffer(-clearance)))
        plate = cards.prisms(pieces(plan), 0.0, lid_thick)
        if cable > 0:
            spot = cable_spot(plan, cable / 2.0)
            hole = Point(spot.x, spot.y).buffer(cable / 2.0, quad_segs=cards.QUAD)
            plate = [cards.boolean("difference",
                                   [m, *cards.prisms([hole], -1.0, lid_thick + 2.0)])
                     for m in plate]
        # Printed inside face down, which is the side the strip is stuck to:
        # the plate side of a print is the flat one, and a strip's adhesive
        # wants a flat one.  No turn, so the move back into the box is a lift.
        parts.append(dict(name="lid", groups=[
            dict(slot="body", element="lid", face="back",
                 mesh=trimesh.util.concatenate(plate))],
            assembled=trimesh.transformations.translation_matrix(
                (0.0, 0.0, depth - lid_thick))))

    for part in parts:
        part["label"] = label or (text or "sign")
        part["card"] = 0
        part["slots"] = cards.slot_meshes(part)
        solids = [part["slots"][s] for s in cards.SLOTS if s in part["slots"]]
        part["mesh"] = solids[0] if len(solids) == 1 else cards.boolean("union", solids)

    stroke = cards.narrowest(lit)
    clear = depth - front - lid_thick
    pockets = len(pieces(inner))
    x0, y0, x1, y1 = cards.extent(shapes)
    info = dict(
        kind="sign", label=label, text="" if svg else text, shape=shape,
        # The face is laid out face down, the way a card is: the side you read
        # points at the build plate.
        front_up=False,
        w=round(float(w), 2), h=round(float(h), 2), thick=round(depth, 2), rise=0.0,
        depth=round(depth, 2), wall=round(wall, 2), front=round(front, 2),
        opaque=round(opaque, 2), diffuse=round(diffuse, 2), clear=round(clear, 2),
        border=round(border, 2) if shape == "letters" else None,
        band=round(border - wall, 2) if shape == "letters" else None,
        bridges=ties, pockets=pockets,
        lid=bool(lid), lid_thick=round(lid_thick, 2) if lid else None,
        clearance=round(clearance, 2) if lid else None,
        cable=round(cable, 2) if (cable and lid) else None,
        margin=round(margin, 2) if shape == "box" else None,
        radius=round(radius, 2), face=cards.FACE, chamfer=round(chamfer, 2),
        cap=round(cap, 2), art=[round(float(x1 - x0), 2), round(float(y1 - y0), 2)],
        shapes=len(lit), stroke=round(float(stroke), 2),
        lit_area=round(100.0 * lit_2d.area / inner.area, 1),
        nozzle=cards.nozzle_for(stroke),
        svg=bool(svg), font=cards.Path(face["path"]).name,
        typeface=face["key"], typeface_name=face["font"], min_cap=face["min_cap"],
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
    info["dim"] = clear < MIN_CLEAR
    info["thin"] = ([] if stroke >= MIN_STROKE else
                    ["the glow" if shape == "letters" else "the letters"]) + \
                   ([] if opaque >= 0.6 else ["the opaque layer"]) + \
                   ([] if wall >= 1.2 else ["the walls"])
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
