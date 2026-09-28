"""A pet collar tag: the name on the front, how to get the pet home on the back.

    parts, info = pettag.build("Biscuit", phone="(555) 214-8890")
    parts, info = pettag.build("Biscuit", phone="(555) 214-8890", shape="bone")
    parts, info = pettag.build("Biscuit", phone="(555) 214-8890", style="slide",
                               collar=20)

Two ways onto a collar:

  * **hanging** -- a disc, a bone, a heart or a plain tag with a ring tab at
    the top, for the split ring or S-hook the collar already has.  Two faces
    to write on, so the name goes on the front and the phone number and the
    QR code on the back, which is the side a stranger turns it over to find.
  * **slide** -- a flat plate with two slots the collar strap threads
    through: in at one slot, behind the plate, out at the other.  Nothing
    dangles, so nothing jingles, snags on a crate or falls off when a split
    ring opens.  The back sits against the dog, so everything is on the front.

A tag is read by a stranger at arm's length, often on a dog that will not
hold still, so the phone number is the line that matters.  It is always set in
the plain sans whatever face the name is in, and the fit is greedy the right
way round: the name starts as large as the tag will take and gives way first,
and the phone number is only shrunk once the name is down to its floor --
with a warning when it goes under PHONE_MIN.

The lettering is **inlaid flush** by default: pockets FACE mm deep in the
body, filled with the lettering colour.  A tag spends its life rubbing on a
collar and a chest, and flush letters have nothing standing up to wear off.
`rise` above 0 raises the front lettering instead, for the look; the back is
always inlaid, because it prints face down and a raised back would need
supports.  So every colour change is in the first and last few layers, and
the body in between prints in one colour.

The parts are the same shape as cards.build()'s, so the plate layout, the 3MF,
the STL and the app's viewer all take them unchanged.
"""
import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polylabel, unary_union

import cards
import typefaces

# Nominal width of a hanging tag.  32 mm is a medium dog; a cat or a toy breed
# wants 25, a big dog 38 to 45.
SIZE = 32.0

# Thick enough not to snap in a mouth, and to hold an inlay on both faces with
# a solid core between them.
THICK = 3.0

# How deep each inlay goes -- the same face layer the fobs use: three layers at
# 0.2 mm, which is where all the colour changes happen.
FACE = cards.FACE

# The ring tab.  Pet hardware is thicker than a keyring's, and a tab that
# tears out is a lost tag, so the wall round the hole is heavier than the
# keyring's 2.2 mm.
RING_D = 5.0
RING_WALL = 2.6

# Clear body between the edge of the tag and the lettering.
MARGIN = 2.0

# The optional border: a band inlaid just inside the edge.
BORDER_IN = 0.9
BORDER_W = 1.1

# Lettering floors, in mm of capital height.  A phone number under PHONE_MIN is
# hard to read on a moving dog; under NOTE_MIN a note is decoration.
NAME_MIN = 4.0
PHONE_CAP = 5.0
PHONE_MIN = 3.5
NOTE_CAP = 3.2
NOTE_MIN = 2.4

# QR modules, in mm.  A millimetre scans easily; QR_MIN is cards' own floor.
QR_MODULE = 1.0
QR_MIN = cards.QR_MIN_MODULE

# The slide-on tag: a plate `SLIDE_W` wide whose height follows the collar,
# with a slot at each end.  The slot is the strap's width plus clearance long,
# and `slot` wide -- the strap's thickness plus room for it to go through twice
# at an angle.
SLIDE_W = 50.0
COLLAR = 20.0           # 3/4 inch, the commonest medium collar
COLLARS = (10.0, 15.0, 20.0, 25.0, 38.0)
SLOT = 3.5
SLOT_EDGE = 3.0         # plate left outside each slot
SLOT_FRAME = 3.5        # plate above and below each slot
SLOT_SLACK = 1.5        # added to the collar width

SHAPES = ("circle", "bone", "heart", "tag")

# Where each shape starts: the smallest size at which "(555) 214-8890" still
# comes out at PHONE_MIN or more on the back.  A disc or a plain tag manages
# that from about 28 mm; a bone's number has only the bar between the lobes,
# and a heart's narrows to its point, so both need about 42.
SIZES = dict(circle=32.0, bone=45.0, heart=42.0, tag=34.0, slide=SLIDE_W)
STYLES = ("hanging", "slide")
SIDES = ("two", "one")

FIT_STEP = 0.95
FIT_MAX = 160


# ---------------------------------------------------------------------------
# outlines
# ---------------------------------------------------------------------------
def outline(shape, size):
    """The tag's shape, `size` mm across, centred on the origin, no tab."""
    s = float(size)
    if shape == "circle":
        return Point(0, 0).buffer(s / 2.0, quad_segs=48)
    if shape == "tag":
        return cards.rounded_rect(s, s * 0.62, s * 0.12)
    if shape == "bone":
        h = s * 0.6
        r = h * 0.28
        cx, cy = s / 2.0 - r, h / 2.0 - r
        lobes = [Point(x, y).buffer(r, quad_segs=32)
                 for x in (-cx, cx) for y in (-cy, cy)]
        bar = cards.box_2d(-cx, -h * 0.31, cx, h * 0.31)
        # Close then open: rounds the waist where the lobes meet the bar, and
        # any point a lobe leaves.
        return unary_union([bar, *lobes]).buffer(1.2, quad_segs=16).buffer(-1.2, quad_segs=16)
    if shape == "heart":
        t = np.linspace(0, 2 * np.pi, 360, endpoint=False)
        x = 16 * np.sin(t) ** 3
        y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
        poly = Polygon(np.column_stack([x, y * 0.92]))
        x0, y0, x1, y1 = poly.bounds
        k = s / (x1 - x0)
        poly = affinity.scale(poly, k, k, origin=(0, 0))
        x0, y0, x1, y1 = poly.bounds
        poly = affinity.translate(poly, -(x0 + x1) / 2.0, -(y0 + y1) / 2.0)
        # A heart has a point at the bottom and a cleft at the top; a sharp
        # point is the first thing to snap, so both get rounded off.
        return poly.buffer(-1.5, quad_segs=16).buffer(1.5, quad_segs=16) \
                   .buffer(1.0, quad_segs=16).buffer(-1.0, quad_segs=16)
    raise ValueError(f"no such tag shape: {shape} -- {', '.join(SHAPES)}")


def top_at(poly, x=0.0):
    """How high the outline reaches straight up from x -- for a heart that is
    the bottom of the cleft, which is where the tab belongs."""
    _, y0, _, y1 = poly.bounds
    cut = poly.intersection(LineString([(x, y0 - 1), (x, y1 + 1)]))
    return max(c[1] for g in getattr(cut, "geoms", [cut]) for c in g.coords)


def ring_tab(base, d=RING_D, wall=RING_WALL):
    """(outline with a tab on top, the hole, the keep-out round it).

    The tab is a disc sitting on the top of the shape, sunk into it so the
    hole's lower rim is a millimetre inside the body: the union is a real
    overlap, and the plastic under the hole -- the bit that takes the pull --
    is the body's, not a thin ring's.
    """
    r = d / 2.0 + wall
    cy = top_at(base) + d / 2.0 - 1.0
    disc = Point(0, cy).buffer(r, quad_segs=32)
    hole = Point(0, cy).buffer(d / 2.0, quad_segs=32)
    return unary_union([base, disc]).buffer(0.8, quad_segs=16).buffer(-0.8, quad_segs=16), \
        hole, disc


def slide_plate(w, collar, slot):
    """(outline, the two slots) for a slide-on tag."""
    slot_len = collar + SLOT_SLACK
    h = slot_len + 2.0 * SLOT_FRAME
    w = max(w, 2.0 * (SLOT_EDGE + slot) + 20.0)
    plate = cards.rounded_rect(w, h, min(5.0, h / 3.0))
    sx = w / 2.0 - SLOT_EDGE - slot / 2.0
    slots = [cards.rounded_rect(slot, slot_len, slot / 2.0, cx=x) for x in (-sx, sx)]
    return plate, slots, w, h


# ---------------------------------------------------------------------------
# fitting the lettering
# ---------------------------------------------------------------------------
REF = 10.0      # rows are traced once at this cap height and then scaled


def text_row(text, font, want, least, role):
    polys, _, _, cap = cards.text_block(text, font, REF, None)
    if not polys:
        return None
    return dict(polys=polys, ref=cap, want=want, least=least, role=role, k=1.0)


def qr_row(link, want=QR_MODULE, least=QR_MIN):
    rows = cards.qr_matrix(link)
    polys = cards.qr_polys(rows, REF)
    return dict(polys=polys, ref=REF, want=want, least=least, role="qr", k=1.0,
                modules=len(rows))


def size_of(row):
    return row["want"] * row["k"]


def stack(rows, anchor):
    """Every row at its current size, stacked top to bottom and centred on
    `anchor`.  Returns [(row, polys)]."""
    placed, y = [], 0.0
    for i, row in enumerate(rows):
        s = size_of(row) / row["ref"]
        polys = [affinity.scale(p, s, s, origin=(0, 0)) for p in row["polys"]]
        x0, y0, x1, y1 = cards.extent(polys)
        if i:
            prev = size_of(rows[i - 1]) if rows[i - 1]["role"] != "qr" else 2.5
            here = size_of(row) if row["role"] != "qr" else 2.5
            y -= 0.45 * min(prev, here) + 0.6
        polys = [affinity.translate(p, -(x0 + x1) / 2.0, y - y1) for p in polys]
        placed.append((row, polys))
        y -= y1 - y0
    ax, ay = anchor
    dy = ay - y / 2.0
    return [(r, [affinity.translate(p, ax, dy) for p in ps]) for r, ps in placed]


def anchors(room):
    """Where a stack of lettering may be centred: on the tag's axis, at a
    spread of heights through the room.  The best single point -- the middle
    of the biggest circle that fits -- is the wrong one for a bone, whose
    biggest circles are in its end lobes, and too low for a heart, whose
    width is all at the top; trying a spread and taking whichever fits is
    simpler than being clever about either."""
    x0, y0, x1, y1 = room.bounds
    strip = room.intersection(cards.box_2d(-(x1 - x0) * 0.15, y0 - 1, (x1 - x0) * 0.15, y1 + 1))
    if strip.geom_type == "MultiPolygon":
        strip = max(strip.geoms, key=lambda g: g.area)
    cy = polylabel(strip, tolerance=0.2).y if not strip.is_empty else (y0 + y1) / 2.0
    span = (y1 - y0) * 0.3
    return [(0.0, cy + span * f) for f in (0, 0.15, -0.15, 0.3, -0.3, 0.5, -0.5, 0.7, -0.7)]


def fit(rows, room):
    """(placed rows, squeezed): the rows shrunk until they sit inside `room`.

    Each pass shrinks whichever row has the most room above its floor, in
    proportion -- so a big name gives way long before a phone number does.
    Only once every row is at its floor does everything shrink together, and
    `squeezed` says so.
    """
    spots = anchors(room)
    fence = room.buffer(1e-6)
    squeezed = False
    for _ in range(FIT_MAX):
        # One stack, moved to each height in turn -- the same shapes, so it is
        # built once and only translated.
        placed = stack(rows, (0.0, 0.0))
        ink = unary_union([p for _, ps in placed for p in ps])
        for ax, ay in spots:
            if affinity.translate(ink, ax, ay).within(fence):
                return [(r, [affinity.translate(p, ax, ay) for p in ps])
                        for r, ps in placed], squeezed
        slack = [(size_of(r) / r["least"], r) for r in rows]
        most, row = max(slack, key=lambda t: t[0])
        if most > 1.0 + 1e-6:
            row["k"] = max(row["k"] * FIT_STEP, row["least"] / row["want"])
        else:
            squeezed = True
            for r in rows:
                r["k"] *= FIT_STEP
    raise ValueError("the lettering will not fit this tag -- a bigger tag, "
                     "a shorter name, or fewer lines")


def phone_lines(phone):
    """The ways a phone number can be set: as given, and -- unless it already
    says where to break -- split at the separator nearest its middle, which is
    what lets a full number sit on a 25 mm disc at a size you can read."""
    out = [phone]
    if phone and "|" not in phone:
        cuts = [i for i, ch in enumerate(phone) if ch in " -." and 0 < i < len(phone) - 1]
        if cuts:
            i = min(cuts, key=lambda c: abs(c - len(phone) / 2.0))
            head, tail = phone[:i + 1].rstrip(" "), phone[i + 1:].lstrip(" -.")
            if phone[i] == "-":
                head = phone[:i + 1]
            out.append(f"{head.strip()}|{tail.strip()}")
    return out


def best_fit(make, phone, room):
    """Fit the side once per way of setting the phone number and keep the one
    that reads best: not squeezed, then the biggest number, then the biggest
    name."""
    best = None
    for text in phone_lines(phone) if phone else [phone]:
        rows = make(text)
        if not rows:
            return [], False
        try:
            placed, squeezed = fit(rows, room)
        except ValueError:
            continue
        caps = {r["role"]: size_of(r) for r, _ in placed}
        score = (not squeezed, round(caps.get("phone", 0.0), 2), caps.get("name", 0.0))
        if best is None or score > best[0]:
            best = (score, placed, squeezed)
    if best is None:
        raise ValueError("the lettering will not fit this tag -- a bigger tag, "
                         "a shorter name, or fewer lines")
    return best[1], best[2]


def side_rows(name, phone, note, link, face_path, sans, room, name_alone):
    rows = []
    _, ry0, _, ry1 = room.bounds
    if name:
        want = (ry1 - ry0) * (0.6 if name_alone else 0.36)
        rows.append(text_row(name, face_path, max(want, NAME_MIN), NAME_MIN, "name"))
    if link:
        rows.append(qr_row(link))
    if phone:
        rows.append(text_row(phone, sans, PHONE_CAP, PHONE_MIN, "phone"))
    if note:
        rows.append(text_row(note, sans, NOTE_CAP, NOTE_MIN, "note"))
    return [r for r in rows if r]


# ---------------------------------------------------------------------------
# the tag
# ---------------------------------------------------------------------------
def flat(polys):
    merged = unary_union(polys)
    return list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]


def solid(polys, z0, t):
    meshes = cards.prisms(flat(polys), z0, t)
    return meshes[0] if len(meshes) == 1 else cards.trimesh.util.concatenate(meshes)


def build(name="", phone="", note="", link="", shape="circle", style="hanging",
          size=None, sides="two", font=None, rise=0.0, border=False,
          ring_d=RING_D, collar=COLLAR, slot=SLOT, thick=THICK,
          colours=cards.COLOURS, label=""):
    """One pet tag, as printable parts plus the numbers worth knowing.

    Returns ([part], info) in cards.build()'s shape.  Colour slots: body, the
    front lettering in primary, the back lettering and QR code in secondary,
    the border in pattern.
    """
    name, phone, note, link = ((v or "").strip() for v in (name, phone, note, link))
    if not name:
        raise ValueError("a pet tag needs a name")
    if style not in STYLES:
        raise ValueError(f"no such style: {style} -- {', '.join(STYLES)}")
    if sides not in SIDES:
        raise ValueError(f"no such side choice: {sides} -- {', '.join(SIDES)}")
    thick = max(2.0, float(thick))
    rise = max(0.0, float(rise))
    face = typefaces.face(font)
    sans = typefaces.face(typefaces.DEFAULT)["path"]

    hole = keep_out = None
    slots = []
    size = float(size) if size else SIZES["slide" if style == "slide" else shape]
    if style == "slide":
        base, slots, w, h = slide_plate(size, float(collar), float(slot))
        body_2d = base.difference(unary_union(slots))
        sides = "one"
        # Behind the plate is the dog; a code there would never be seen.
        link = ""
    else:
        base = outline(shape, max(18.0, size))
        if ring_d > 0.5:
            body_2d, hole, keep_out = ring_tab(base, float(ring_d))
            body_2d = body_2d.difference(hole)
        else:
            body_2d = base

    margin = MARGIN + (BORDER_IN + BORDER_W + 0.6 if border else 0.0)
    room = base.buffer(-margin, quad_segs=16)
    if keep_out is not None:
        room = room.difference(keep_out.buffer(margin * 0.5))
    for s in slots:
        room = room.difference(s.buffer(margin))
    if room.geom_type == "MultiPolygon":
        room = max(room.geoms, key=lambda g: g.area)
    if room.is_empty or room.area < 20:
        raise ValueError("no room left on the tag for lettering -- make it bigger")

    # What goes where.  Two sides: the name alone on the front, everything
    # that gets the pet home on the back.  One side: all of it on the front,
    # and a QR code, if asked for, on the back on its own.
    def rows(n, p, t, q, alone):
        return lambda ph: side_rows(n, ph if p else "", t, q, face["path"], sans,
                                    room, alone)
    if sides == "two":
        front, front_phone = rows(name, False, "", "", True), ""
        back, back_phone = rows("", True, note, link, False), phone
    else:
        front, front_phone = rows(name, True, note, "", False), phone
        back, back_phone = rows("", False, "", link, False), ""

    front_placed, front_squeezed = best_fit(front, front_phone, room)
    back_placed, back_squeezed = best_fit(back, back_phone, room)

    # The back is read with the tag turned over left to right, so it is drawn
    # as you would see it and then mirrored into the tag's own coordinates.
    back_placed = [(r, [affinity.scale(p, -1, 1, origin=(0, 0)) for p in ps])
                   for r, ps in back_placed]

    ring_2d = None
    if border:
        ring_2d = base.buffer(-BORDER_IN, quad_segs=16).difference(
            base.buffer(-(BORDER_IN + BORDER_W), quad_segs=16))
        if keep_out is not None:
            ring_2d = ring_2d.difference(keep_out.buffer(0.4))
        for s in slots:
            ring_2d = ring_2d.difference(s.buffer(1.2))

    # The body, with every inlay's pocket taken out of it.  Pockets go a
    # little past the face so the cut is clean; the inlays sit a hundredth
    # into the floor so the parts overlap rather than kiss.
    body = cards.prisms([body_2d], 0.0, thick)[0]
    raised = rise > 0
    cutters, groups_ = [], []
    front_polys = {}
    for row, ps in front_placed:
        front_polys.setdefault(row["role"], []).extend(ps)
    if ring_2d is not None and not ring_2d.is_empty:
        front_polys["border"] = [ring_2d]
    for role, ps in front_polys.items():
        colour = "pattern" if role == "border" else "primary"
        if raised:
            mesh = solid(ps, thick - 0.01, rise + 0.01)
        else:
            cutters.append(solid(ps, thick - FACE, FACE + 1.0))
            mesh = solid(ps, thick - FACE - 0.01, FACE + 0.01)
        groups_.append(dict(slot=colour, element=role, face="front", mesh=mesh))
    back_polys = {}
    for row, ps in back_placed:
        back_polys.setdefault(row["role"], []).extend(ps)
    for role, ps in back_polys.items():
        cutters.append(solid(ps, -1.0, FACE + 1.0))
        groups_.append(dict(slot="secondary", element=role, face="back",
                            mesh=solid(ps, 0.0, FACE + 0.01)))
    if cutters:
        body = cards.boolean("difference", [body, *cutters])
    groups_.insert(0, dict(slot="body", element="body", face="body", mesh=body))

    part = dict(name="", label=label or name, card=0, groups=groups_,
                assembled=np.eye(4))
    part["slots"] = cards.slot_meshes(part)
    solids = [part["slots"][s] for s in cards.SLOTS if s in part["slots"]]
    part["mesh"] = solids[0] if len(solids) == 1 else cards.boolean("union", solids)
    parts = [part]

    # The numbers worth knowing: how big everything came out, and whether the
    # phone number is still something a stranger can read.
    def cap_of(role, placed):
        return next((round(size_of(r), 2) for r, _ in placed if r["role"] == role), None)

    everything = front_placed + back_placed
    qr = next(((r["modules"], round(size_of(r), 2)) for r, _ in back_placed
               if r["role"] == "qr"), None)
    ink = [p for r, ps in everything if r["role"] != "qr" for p in ps]
    stroke = cards.narrowest(flat(ink)) if ink else 0.0
    x0, y0, x1, y1 = body_2d.bounds
    thin = []
    phone_cap = cap_of("phone", everything)
    if phone and phone_cap is not None and phone_cap < PHONE_MIN - 1e-6:
        thin.append("phone number")
    if front_squeezed or back_squeezed:
        thin.append("lettering")
    colour_slots = sorted({g["slot"] for g in groups_}, key=cards.SLOTS.index)
    total = float(part["mesh"].bounds[1][2])
    bands = [[0.0, round(FACE, 2)]] if back_placed else []
    bands.append([round(thick - (0 if raised else FACE), 2), round(total, 2)])
    info = dict(
        kind="pet", label=label, text=name,
        front_up=True, style=style, shape="slide" if style == "slide" else shape,
        sides=sides,
        w=round(x1 - x0, 2), h=round(y1 - y0, 2), thick=round(thick, 2),
        rise=round(rise, 2), total_z=round(total, 2),
        name_cap=cap_of("name", everything), phone_cap=phone_cap,
        note_cap=cap_of("note", everything),
        qr=dict(modules=qr[0], module=qr[1], size=round(qr[0] * qr[1], 2)) if qr else None,
        ring=hole is not None, ring_d=float(ring_d) if hole is not None else None,
        # where the split ring goes through, for the product shot
        hole=[round(hole.centroid.x, 3), round(hole.centroid.y, 3), float(ring_d)]
        if hole is not None else None,
        collar=float(collar) if style == "slide" else None,
        slot=float(slot) if style == "slide" else None,
        border=bool(border),
        typeface=face["key"], typeface_name=face["font"],
        stroke=round(float(stroke), 2), nozzle=cards.nozzle_for(stroke) if ink else None,
        slots=colour_slots, part_slots={"tag": colour_slots}, parts=["tag"], pins=0,
        part_thick=round(total, 2), assembled=round(total, 2),
        pocket=[0.0, 0.0, 0.0], tag_mode="none", joint=None, tag=[0, 0, 0],
        colour_bands=bands, colour_z=round(FACE, 2),
        volume=round(part["mesh"].volume / 1000.0, 2),
        watertight=part["mesh"].is_watertight and part["mesh"].is_winding_consistent,
        thin=thin, face=FACE, chamfer=0.0, layout=None, look=None,
    )
    return parts, info


# ---------------------------------------------------------------------------
# the product shot
# ---------------------------------------------------------------------------
# A split ring for the product shot: two turns of steel wire.  Sized off the
# tag's own hole, so the wire fills it the way a real one does.
RING_WIRE = 1.1          # wire thickness, mm
RING_ACROSS = 20.0       # outside diameter of the ring, mm
STEEL = "#cfd1d4"


def linear_rgba(hexc):
    """A #rrggbb colour as the linear RGBA a glTF base colour is.  Written
    straight from the hex, a navy tag shows up light blue: glTF colours are
    linear, and the viewer converts them back to sRGB for the screen."""
    out = []
    for i in (0, 2, 4):
        c = int(hexc.lstrip("#")[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out + [1.0]


def split_ring(hole, wire=RING_WIRE, across=RING_ACROSS, turns=2.0, lean=None,
               thick=THICK):
    """A split ring through `hole` ([x, y, d]), as a trimesh.

    The ring stands in the plane across the tag -- y up, z through it -- with
    its lowest point in the hole, and two turns of wire side by side along x,
    the way the coils of a real one sit.  `lean` turns it about the vertical
    through the hole, so it reads as a ring rather than a line edge-on; the
    lowest point stays where it is, in the hole.  Left alone it turns as far
    as the hole lets it, less a margin: leant further, a ring of this wire
    would pass through the plastic.
    """
    import trimesh
    wire = min(wire, hole[2] * 0.3)          # two coils side by side, and room round them
    if lean is None:
        room = hole[2] / 2.0 - wire * 1.05 / 2.0 - wire / 2.0
        lean = max(0.2, min(0.85, 0.95 * float(np.arctan2(max(room, 0.0), thick / 2.0))))
    r = across / 2.0 - wire / 2.0
    cx, cy = hole[0], hole[1] + r
    n = int(96 * turns)
    t = np.linspace(0.0, 2 * np.pi * turns, n)
    # start and finish at the bottom, which is where the ring passes through
    path = np.column_stack([cx + (t / (2 * np.pi) - turns / 2) * wire * 1.05,
                            cy - r * np.cos(t), r * np.sin(t)])
    profile = Point(0, 0).buffer(wire / 2.0, quad_segs=6)
    ring = trimesh.creation.sweep_polygon(profile, path)
    turn = trimesh.transformations.rotation_matrix(lean, [0, 1, 0], [hole[0], hole[1], 0])
    ring.apply_transform(turn)
    return ring


def product_glb(parts, info, colours):
    """The tag as a GLB for the page's product shot: every colour a part in
    its own filament colour, and a steel split ring through the hole when
    it has one.  The tag's front is +z and its tab is up (+y), which is how it
    hangs."""
    import io
    import trimesh

    part = parts[0]
    scene = trimesh.Scene()
    thick = info["thick"]
    for slot, mesh in part["slots"].items():
        m = mesh.copy()
        m.apply_translation((0, 0, -thick / 2.0))          # centred on its own thickness
        m.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            name=slot, baseColorFactor=linear_rgba(colours[cards.SLOTS.index(slot)]),
            metallicFactor=0.0, roughnessFactor=0.42))
        scene.add_geometry(m, node_name=f"tag-{slot}", geom_name=f"tag-{slot}")
    if info.get("hole"):
        ring = split_ring(info["hole"], thick=thick)
        ring.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            name="steel", baseColorFactor=linear_rgba(STEEL),
            metallicFactor=1.0, roughnessFactor=0.22))
        scene.add_geometry(ring, node_name="ring", geom_name="ring")
    buf = io.BytesIO()
    buf.write(scene.export(file_type="glb"))
    return buf.getvalue()


def parse_batch(text):
    """One pet per line: name, phone, note, link -- tabs or commas.  A line
    starting with # is a comment."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cells = [c.strip() for c in (line.split("\t") if "\t" in line else line.split(","))]
        cells += [""] * (4 - len(cells))
        if not cells[0]:
            raise ValueError(f"no name on this line: {raw!r}")
        rows.append(dict(name=cells[0], phone=cells[1], note=cells[2], link=cells[3]))
    return rows


def build_batch(rows, **kw):
    """One tag per row, labelled by name; one list, one plate.  A row's own
    phone, note or link wins over the shared one."""
    parts, infos = [], []
    for i, row in enumerate(rows):
        args = dict(kw)
        for k in ("phone", "note", "link"):
            if row.get(k):
                args[k] = row[k]
        p, info = build(row["name"], label=row["name"], **args)
        for part in p:
            part["card"] = i
        parts += p
        infos.append(info)
    return parts, infos
