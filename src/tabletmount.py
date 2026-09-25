"""A tablet holder: a tray the iPad slides into, two caps, and a clamp.

    parts, info = tabletmount.build("mini-2")
    parts, info = tabletmount.build("mini-4", bore=25, mount="clamp")

Not a case. A case wraps the iPad and goes wherever it goes; this holds it in
one place -- on a stand, a pole, a cart, a wall arm -- and is built to be
bolted to something. Three parts:

  1. the **tray**: a back plate with a side wall down each long edge, and a
     flat shelf at each end past the iPad. The iPad drops in from the front.
  2. two **caps**, one on each shelf. Each is a bar across the width with a
     lip that comes forward over the bezel, so with both on the iPad is held
     at both ends from in front. Four M3 x 10 countersunk screws come up
     through the shelves into them. Take the bottom cap off and the iPad
     slides out.
  3. a **clamp** on the top cap: a block with a round bore through it, front
     to back, and a thumbscrew coming in from the side against whatever goes
     through the bore. The thumbscrew is an M6 with a nut trapped in the
     block; the slot for the nut opens on the back face, so the nut drops in
     from behind.

Why the lips are on separate caps rather than on the tray. A lip over the
glass is a ledge in mid air: printed back down, which a tray has to be, a
12 mm ledge 10 mm off the plate is a thing that droops or needs support. A
cap printed face down has its lip flat on the plate, and there is nothing to
support anywhere in it. The side walls carry no lip at all for the same
reason; with both ends held, they only have to stop the iPad sliding
sideways, and they come up flush with the glass to do it.

Holes, which are estimates: every number below that is not the body size is
guessed from photos, and nothing here has been measured against a real iPad.
They are cut generously -- a 20 mm notch for a 10.5 mm home button -- so a
millimetre of error in where one is still leaves it clear.

Frame: ``x`` across, ``y`` along, as you look at the screen in portrait with
the home button at the bottom; ``z`` up from the back face of the tray. The
rear camera is top-left seen from behind, so top-right (+x, +y) here.
"""
import math

import numpy as np
import trimesh
from shapely.geometry import Point

import cards


# ---------------------------------------------------------------------------
# the iPads
# ---------------------------------------------------------------------------
# length, width, thickness are Apple's published figures.  `end` is the bezel
# above and below the screen in portrait, which is how far a cap's lip can
# come forward before it covers something you need to see.  `home` is whether
# there is a home button to leave a notch for.
DEVICES = {
    "mini-1": dict(name="iPad mini (1st gen)", length=200.0, width=134.7,
                   thick=7.2, end=19.6, home=True, jack=True, switch=True,
                   port=14.0),
    "mini-2": dict(name="iPad mini 2 / 3", length=200.0, width=134.7,
                   thick=7.5, end=19.6, home=True, jack=True, switch=True,
                   port=14.0),
    "mini-4": dict(name="iPad mini 4 / 5", length=203.2, width=134.8,
                   thick=6.1, end=21.2, home=True, jack=True, switch=False,
                   port=14.0),
    "mini-6": dict(name="iPad mini 6 / 7", length=195.4, width=134.8,
                   thick=6.3, end=8.0, home=False, jack=False, switch=False,
                   port=16.0),
}
DEFAULT = "mini-2"

# The fit.  0.4 mm round the iPad is a drop-in fit that does not rattle; the
# pocket's corners are 3 mm, tighter than any iPad's, so a corner of the tray
# can never be the thing that stops it going in.
CLEARANCE = 0.4
POCKET_R = 3.0

# The tray.  2.4 mm of back is six layers and stiff enough to hang 300 g off
# at one end; 3 mm walls are seven lines of a 0.4 mm nozzle.
BACK = 2.4
WALL = 3.0
SHELF = 12.0          # each end, past the iPad: what a cap sits on
RADIUS = 6.0          # outer corners, seen from the front

# The caps.
LIP = 2.4             # thickness of the lip over the glass
OVER = 12.0           # how far the lip comes forward, at most
SCREW_HOLE = 3.4      # through the shelf, for an M3
SCREW_HEAD = 6.6      # countersink at the back face
PILOT = 2.6           # into the cap, for an M3 to cut its own thread
PILOT_DEPTH = 8.0

# The clamp.  The bore is the number to change: it is whatever the holder is
# going onto.  20 mm is a guess at the one in the photo it was drawn from.
BORE = 20.0
BORE_SLACK = 0.4      # on the diameter, so it slides on before it is tightened
CLAMP_DEPTH = 22.0    # front to back: how long the bore is
SCREW_M6 = 6.5        # clearance for the thumbscrew
NUT_AF = 10.3         # an M6 nut is 10 mm across the flats
NUT_THICK = 5.6
MOUNTS = ("clamp", "none")

# Nothing between the bore or a hole and the outside is allowed thinner than
# this; the clamp grows to keep it.
MIN_WEB = 4.0


def box(x0, x1, y0, y1, z0, z1):
    """An axis-aligned box from its extents: every solid here is mostly these."""
    return trimesh.creation.box(bounds=[[x0, y0, z0], [x1, y1, z1]])


def cylinder_z(x, y, r, z0, z1, sections=64):
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=sections)
    c.apply_translation((x, y, (z0 + z1) / 2.0))
    return c


def cylinder_x(x0, x1, y, z, r, sections=48):
    c = trimesh.creation.cylinder(radius=r, height=x1 - x0, sections=sections)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0, 1, 0)))
    c.apply_translation(((x0 + x1) / 2.0, y, z))
    return c


def cone_z(x, y, r0, z0, r1, z1, sections=48):
    """A countersink: radius r0 at z0 narrowing to r1 at z1."""
    ring0 = Point(x, y).buffer(r0, quad_segs=sections // 4)
    ring1 = Point(x, y).buffer(r1, quad_segs=sections // 4)
    return cards.loft(ring0, z0, ring1, z1)


def hex_x(x0, x1, y, z, af):
    """A nut pocket: a hexagonal prism along x, flats top and bottom."""
    r = af / math.sqrt(3.0)                       # centre to corner
    pts = [(y + r * math.cos(a), z + r * math.sin(a))
           for a in np.radians([0, 60, 120, 180, 240, 300])]
    from shapely.geometry import Polygon
    prism = trimesh.creation.extrude_polygon(Polygon(pts), x1 - x0)
    # extruded along z in (y, z) -> turn it so the extrusion runs along x
    prism.apply_transform(np.array([[0, 0, 1, 0], [1, 0, 0, 0],
                                    [0, 1, 0, 0], [0, 0, 0, 1]], float))
    prism.apply_translation((x0, 0.0, 0.0))
    return prism


def diff(body, cuts):
    cuts = [c for c in cuts if c is not None]
    return cards.boolean("difference", [body, *cuts]) if cuts else body


def build(device=DEFAULT, clearance=CLEARANCE, back=BACK, wall=WALL,
          over=OVER, mount="clamp", bore=BORE, clamp_depth=CLAMP_DEPTH,
          camera=True, colours=cards.COLOURS, label=""):
    """The holder for one iPad, as printable parts plus the numbers worth knowing.

    Returns ([tray, top cap, bottom cap], info) in cards.build()'s shape, so
    the plate layout, the 3MF, the STL and the app's viewer take it unchanged.
    """
    if device not in DEVICES:
        raise ValueError(f"no such iPad: {device!r} -- it is one of "
                         + ", ".join(DEVICES))
    mount = (mount or "none").strip().lower()
    if mount not in MOUNTS:
        raise ValueError(f"no such mount: {mount!r} -- it is one of "
                         + ", ".join(MOUNTS))
    dev = DEVICES[device]
    clearance = min(1.2, max(0.1, float(clearance)))
    back = min(6.0, max(1.2, float(back)))
    wall = min(8.0, max(1.2, float(wall)))
    bore = min(45.0, max(6.0, float(bore)))
    clamp_depth = min(40.0, max(12.0, float(clamp_depth)))

    # A lip that reaches the screen covers the screen: stop it 3 mm short of
    # the bezel's inner edge.  Less than 3 mm of lip holds nothing.
    over_max = dev["end"] - 3.0
    over = min(float(over), over_max)
    if over < 3.0:
        raise ValueError(f"the {dev['name']} has a {dev['end']:g} mm bezel: no "
                         "room for a lip over it")

    pw = dev["width"] + 2 * clearance              # the pocket
    pl = dev["length"] + 2 * clearance
    depth = dev["thick"] + clearance
    ow, ol = pw + 2 * wall, pl + 2 * SHELF         # the tray outside
    top = back + depth                             # glass, and the wall tops
    face = top + LIP                               # front of the caps
    hw, hl = pw / 2.0, pl / 2.0

    # The outline everything is trimmed to, seen from the front.
    outline = cards.rounded_rect(ow, ol, RADIUS)
    fence = cards.prisms([outline], -1.0, face + 2.0)[0]

    # ---- the tray -----------------------------------------------------
    plate = cards.prisms([outline], 0.0, back)[0]
    walls = [box(-ow / 2 - 1, -hw, -hl, hl, back - 0.01, top),
             box(hw, ow / 2 + 1, -hl, hl, back - 0.01, top)]
    tray = cards.boolean("intersection",
                         [cards.boolean("union", [plate, *walls]), fence])
    cuts = []
    # The pocket's floor corners: the plate is flat, so only the walls meet
    # the pocket, and they meet it square -- a 3 mm radius there would only
    # matter at the ends, where there is no wall.  So nothing to do.
    if camera:
        cx, cy = dev["width"] / 2 - 9.0, dev["length"] / 2 - 9.0
        cuts.append(cylinder_z(cx, cy, 7.0, -1.0, back + 1.0))
    # Volume buttons (and the switch, where there is one) are on the right
    # edge near the top: a notch in the wall from just above the plate.
    run = 55.0 if dev["switch"] else 40.0
    cuts.append(box(hw - 0.5, ow / 2 + 1, hl - 18.0 - run, hl - 18.0,
                    back + 1.2, top + 1.0))

    # Screws: two per cap, up through the shelf, countersunk at the back.
    screws = {
        # the top cap has the jack at one end and the top button at the
        # other, so its screws sit inboard of both
        "top": [(-0.23 * ow, hl + SHELF / 2), (0.23 * ow, hl + SHELF / 2)],
        # the bottom has the port and the speakers across the middle, so its
        # go out at the ends
        "bottom": [(-(ow / 2 - 9.0), -(hl + SHELF / 2)),
                   (ow / 2 - 9.0, -(hl + SHELF / 2))],
    }
    head_depth = (SCREW_HEAD - SCREW_HOLE) / 2.0   # 90-degree countersink
    for x, y in screws["top"] + screws["bottom"]:
        cuts.append(cylinder_z(x, y, SCREW_HOLE / 2, -1.0, back + 1.0, 32))
        cuts.append(cone_z(x, y, SCREW_HEAD / 2 + 0.01, -0.01,
                           SCREW_HOLE / 2, head_depth))
    tray = diff(tray, cuts)

    # ---- the caps -----------------------------------------------------
    def cap(sign, notch, channels, holes):
        """One end: a bar on the shelf and a lip forward over the bezel.

        ``sign`` is +1 for the top, -1 for the bottom. ``channels`` are
        (x centre, width) cuts right through the bar for whatever is on that
        edge of the iPad -- a port, a jack, a grille, a button.
        """
        y_in, y_out = sign * hl, sign * (ol / 2 + 1)
        bar = box(-ow / 2 - 1, ow / 2 + 1, min(y_in, y_out), max(y_in, y_out),
                  back, face)
        y_lip = sign * (hl - over)
        lip = box(-ow / 2 - 1, ow / 2 + 1, min(y_lip, y_in), max(y_lip, y_in),
                  top, face)
        body = cards.boolean("intersection",
                             [cards.boolean("union", [bar, lip]), fence])
        cuts = []
        if notch:
            # Right through the lip, for the front camera or the home
            # button, so the bezel shows through and the button can be
            # pressed.
            cuts.append(box(-notch / 2, notch / 2, min(y_lip, y_in) - 0.5,
                            max(y_lip, y_in) + 0.5, top - 0.5, face + 1))
        for x, w in channels:
            cuts.append(box(x - w / 2, x + w / 2, min(y_in, y_out) - 1,
                            max(y_in, y_out) + 1, back - 1, top))
        for x, y in holes:
            # as deep as the bar allows, leaving a skin over the end
            deep = min(PILOT_DEPTH, face - back - 1.0)
            cuts.append(cylinder_z(x, y, PILOT / 2, back - 1, back + deep, 24))
        return diff(body, cuts)

    half = dev["width"] / 2
    top_channels = []
    if dev["jack"]:
        top_channels.append((-(half - 12.0), 11.0))     # headphone jack
    top_channels.append((half - 17.0, 18.0))            # top button
    bottom_channels = [(0.0, dev["port"] + 2.0),        # the port and a plug
                       (-27.0, 22.0), (27.0, 22.0)]     # speakers either side

    top_cap = cap(+1, 16.0, top_channels, screws["top"])
    bottom_cap = cap(-1, 20.0 if dev["home"] else 0.0, bottom_channels,
                     screws["bottom"])

    # ---- the clamp ----------------------------------------------------
    clamp = None
    if mount == "clamp":
        rb = bore / 2.0 + BORE_SLACK / 2.0
        # Wide enough for the nut and its web beside the bore on the screw
        # side, the same on the other so it is symmetric; long enough for a
        # web beyond the bore.
        side = max(MIN_WEB + NUT_THICK + MIN_WEB, 8.0)
        bw = 2 * (rb + side)
        reach = 2 * rb + 2 * MIN_WEB + 2.0
        y0, y1 = ol / 2, ol / 2 + reach
        z0 = face - max(clamp_depth, face)
        bc = (y0 + y1) / 2                        # bore centre
        # The block starts where the tray ends; a sliver of it reaches back
        # into the cap, above the shelf, so the two are one solid rather
        # than two that touch.
        block = cards.boolean("union", [
            box(-bw / 2, bw / 2, y0, y1, z0, face),
            box(-bw / 2, bw / 2, y0 - 1.0, y0 + 0.5, back, face)])
        zc = (z0 + face) / 2
        cuts = [cylinder_z(0.0, bc, rb, z0 - 1, face + 1),
                cylinder_x(rb - 1.0, bw / 2 + 1, bc, zc, SCREW_M6 / 2)]
        # The nut sits in the web between the bore and the +x face, in a
        # slot that runs out through the back face so it drops in from
        # behind; it cannot turn in there, so the thumbscrew threads into it.
        nx = rb + MIN_WEB
        cuts.append(hex_x(nx, nx + NUT_THICK, bc, zc, NUT_AF))
        cuts.append(box(nx, nx + NUT_THICK, bc - NUT_AF / 2, bc + NUT_AF / 2,
                        z0 - 1, zc))
        clamp = diff(block, cuts)
        top_cap = cards.boolean("union", [top_cap, clamp])

    # ---- as printed ---------------------------------------------------
    # The tray prints as it is, back down. A cap turns over onto its face,
    # which puts the lip flat on the plate, and a quarter turn so that it
    # lies along y beside the tray rather than across it.
    def face_down(mesh):
        """(mesh in print pose, 4x4 from print pose back to assembled)."""
        flip = trimesh.transformations.rotation_matrix(math.pi, (0, 1, 0))
        turn = trimesh.transformations.rotation_matrix(math.pi / 2, (0, 0, 1))
        to_print = turn @ flip
        m = mesh.copy()
        m.apply_transform(to_print)
        lift = trimesh.transformations.translation_matrix(
            (0.0, 0.0, -m.bounds[0][2]))
        m.apply_transform(lift)
        return m, np.linalg.inv(lift @ to_print)

    parts = [dict(name="tray", groups=[
        dict(slot="body", element="body", face="back", mesh=tray)],
        assembled=np.eye(4))]
    for name, mesh in (("cap-top", top_cap), ("cap-bottom", bottom_cap)):
        printed, back_home = face_down(mesh)
        parts.append(dict(name=name, groups=[
            dict(slot="body", element=name, face="front", mesh=printed)],
            assembled=back_home))

    for part in parts:
        part["label"] = label or dev["name"]
        part["card"] = 0
        part["slots"] = cards.slot_meshes(part)
        part["mesh"] = part["slots"]["body"]

    total_l = ol + (reach if clamp is not None else 0.0)
    info = dict(
        kind="tablet", label=label, text="", device=device,
        device_name=dev["name"], front_up=True,
        w=round(ow, 2), h=round(total_l, 2), thick=round(face, 2),
        depth=round(depth, 2), rise=0.0,
        pocket=[round(pw, 2), round(pl, 2), round(depth, 2)],
        clearance=round(clearance, 2), back=round(back, 2), wall=round(wall, 2),
        over=round(over, 2), lip=LIP, shelf=SHELF,
        mount=mount, bore=round(bore, 2) if clamp is not None else None,
        clamp_depth=round(max(clamp_depth, face), 2) if clamp is not None else None,
        screws="4 x M3 x 10 countersunk", thumbscrew="M6 thumbscrew and nut"
        if clamp is not None else None,
        home=dev["home"], camera=bool(camera),
        slots=["body"], part_slots={p["name"]: ["body"] for p in parts},
        parts=[p["name"] for p in parts], pins=0,
        part_thick=round(max(p["mesh"].bounds[1][2] for p in parts), 2),
        assembled=round(face, 2), tag_mode="none", joint=None, tag=[0, 0, 0],
        lines={}, logo=None, qr=None, pause_z=None, colour_z=0.0,
        colour_bands=[], nozzle=None, thin=[],
        volume=round(sum(p["mesh"].volume for p in parts) / 1000.0, 2),
        watertight=all(p["mesh"].is_watertight and p["mesh"].is_winding_consistent
                       for p in parts),
    )
    info["grams"] = round(info["volume"] * 1.24, 0)
    info["total_z"] = round(float(max(p["mesh"].bounds[1][2] for p in parts)), 2)
    lo, hi = cards.plate(parts).bounds
    info["plate_size"] = [round(float(v), 1) for v in hi - lo]
    return parts, info
