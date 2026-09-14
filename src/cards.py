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

# The NFC tag the pocket is cut for.  Default is a rectangular NTAG213
# sticker; measure yours, the sizes vary a lot between sellers.
TAG = dict(w=35.0, h=22.0, thick=0.5, clearance=0.4, corner=1.5)

CARD = dict(
    label="card",
    w=85.6, h=54.0, corner=3.18,    # CR80: the outline of a credit card
    thick=2.2, split_thick=2.6, rise=0.6,
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
    thick=2.8, split_thick=3.2, rise=0.6,
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


def front_face(spec, w, h, fields, font):
    """Name, company, rule and phone, stacked and centred in the content box.

    Laid out as read; build() mirrors it, because this face ends up pointing
    at the build plate.
    """
    x0, x1, y0, y1 = content_box(spec, w, h, mirrored=True)
    inner_w = x1 - x0
    rows, gaps, measured = [], [], {}
    for key, cap in spec["rows"]:
        if key == "rule":
            if not rows:
                continue
            polys = [box(-inner_w * 0.22, -cap / 2.0, inner_w * 0.22, cap / 2.0)]
        else:
            if not fields.get(key):
                continue
            polys, _, height, cap = text_block(
                fields[key], font, cap, inner_w,
                tracking=0.0 if key == "name" else 0.02)
            if not polys:
                continue
            measured[key] = dict(cap=round(cap, 2), stroke=round(narrowest(polys), 2),
                                 lines=fields[key].count("|") + fields[key].count("\n") + 1)
            cap = height
        if rows:
            gaps.append(spec["gaps"][min(len(rows) - 1, len(spec["gaps"]) - 1)])
        rows.append((polys, cap))

    polys = stack(rows, gaps, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
    if spec["border"]:
        inset = spec["border_inset"]
        polys.append(frame(w - 2 * inset, h - 2 * inset,
                           max(spec["corner"] - inset, 0.8), spec["border"]))
    return polys, measured


def back_face(spec, w, h, pocket_w, pocket_h, tap_text, font):
    """The tag pocket plus the contactless mark: beside the pocket when there
    is room next to it, under it when there is not.

    Laid out as seen from the back, which is also how it is built -- this face
    ends up pointing +Z.
    """
    x0, x1, y0, y1 = content_box(spec, w, h)
    inner_w, inner_h = x1 - x0, y1 - y0
    gap = 3.0

    marks = contactless(spec["symbol"])
    mx0, _, mx1, _ = extent(marks)
    sym_w, sym_h = mx1 - mx0, spec["symbol"]

    beside = inner_w - pocket_w - gap
    if beside >= sym_w and pocket_h <= inner_h:
        zone_w, zone_h = beside, inner_h
        pocket_c = (x0 + pocket_w / 2.0, (y0 + y1) / 2.0)
        block_c = (x1 - zone_w / 2.0, (y0 + y1) / 2.0)
    elif pocket_w <= inner_w and pocket_h + gap + sym_h <= inner_h:
        zone_w, zone_h = inner_w, inner_h - pocket_h - gap
        pocket_c = ((x0 + x1) / 2.0, y1 - pocket_h / 2.0)
        block_c = ((x0 + x1) / 2.0, y0 + zone_h / 2.0)
    else:
        raise ValueError(
            f"a {pocket_w:.1f} x {pocket_h:.1f} mm pocket and a {sym_w:.0f} x "
            f"{sym_h:.0f} mm mark do not both fit in the {inner_w:.1f} x "
            f"{inner_h:.1f} mm back of the {spec['label']} -- use a smaller tag, "
            f"or the fob, which grows to fit")

    # Lettering that has had to shrink this far is neither readable nor
    # printable, and the arcs say the same thing without it.
    tap, tap_h = [], 0.0
    if tap_text:
        tap, _, tap_h, tap_cap = text_block(tap_text, font, spec["tap_cap"], zone_w,
                                            tracking=0.06)
        if tap and (tap_cap < 2.2 or sym_h + 1.8 + tap_h > zone_h):
            tap, tap_h = [], 0.0

    block_h = sym_h + (1.8 + tap_h if tap else 0.0)
    bx, by = block_c
    top = by + block_h / 2.0
    marks = [affinity.translate(p, bx, top - sym_h / 2.0) for p in marks]
    marks += [affinity.translate(p, bx, top - sym_h - 1.8 - tap_h / 2.0) for p in tap]
    return rounded_rect(pocket_w, pocket_h, TAG["corner"], *pocket_c), marks, len(tap)


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


def plate(parts, gap=6.0):
    """The parts laid out side by side on one build plate, as a single mesh.

    They are disjoint solids, so this is a concatenation rather than a boolean
    -- every slicer reads it as a multi-part object.
    """
    out, x = [], 0.0
    for _, mesh in parts:
        mesh = mesh.copy()
        lo, hi = mesh.bounds
        mesh.apply_translation((x - lo[0], -(lo[1] + hi[1]) / 2.0, -lo[2]))
        out.append(mesh)
        x += hi[0] - lo[0] + gap
    return trimesh.util.concatenate(out) if len(out) > 1 else out[0]


def build(kind, name="", company="", phone="", font=None, tag=None,
          tap_text="TAP HERE", tag_mode="pocket", lid=0.6, border=True):
    """One card or fob as printable parts, plus the numbers worth knowing.

    Returns ([(suffix, mesh), ...], info) -- one part for the solid modes, two
    for "split".  Every part comes out lying down, relief face at z = 0, which
    is how to print it: lettering face-down gets the build-plate finish, and
    nothing has to bridge over the tag cavity.

    tag_mode picks how the tag goes in:

      pocket  an open recess in the back; stick the tag in afterwards.
      embed   the same recess roofed over with `lid` mm; bury the tag by
              pausing the print at the height this reports.
      split   two half-thickness parts to glue together with the tag sandwiched
              between them, register pins on the joint.  The tag ends up on the
              neutral plane with plastic either side, which is the strongest of
              the three and the only one where nothing of the tag shows.
    """
    spec = {**BODIES[kind]}
    font = font or default_font()
    t = {**TAG, **(tag or {})}
    if not border:
        spec["border"] = 0.0
    split = tag_mode == "split"

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
    if spec["grow"]:            # the fob is sized by the tag, not the other way round
        x0, x1, _, _ = content_box(spec, w, h)
        sym_w = np.diff(extent(contactless(spec["symbol"]))[0::2])[0]
        # 0.2 mm of slack: growing to exactly the width back_face() asks for
        # leaves the fit test to decide on floating-point noise.
        w += max(0.0, pocket_w + sym_w + 3.2 - (x1 - x0))
        h = max(h, pocket_h + 2 * spec["margin"])

    fields = dict(name=name, company=company, phone=phone)
    front, measured = front_face(spec, w, h, fields, font)
    pocket, marks, n_tap = back_face(spec, w, h, pocket_w, pocket_h, tap_text, font)
    # Both faces are laid out the way you read them.  The back ends up facing
    # +Z and needs nothing done to it; the front faces the build plate, so it
    # is mirrored -- which is exactly what turning the card over does to it.
    front = [affinity.scale(p, -1.0, 1.0, origin=(0, 0)) for p in front]

    rise = spec["rise"]
    z_body, z_back = rise, rise + thick     # the front face and back face of the slab
    outline = rounded_rect(w, h, spec["corner"])

    solids = prisms([outline], z_body, thick)
    solids += prisms(front, 0.0, rise + 0.01)
    solids += prisms(marks, z_back - 0.01, rise + 0.01)
    solid = boolean("union", solids)

    if split:                   # cavity straddling the joint, half in each part
        z_mid = z_body + thick / 2.0
        cavity = (z_mid - depth / 2.0, depth)
        pause_z = None
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
    mesh = boolean("difference", [solid, *cuts])

    pins = []
    if split:
        blocked = pocket if hole is None else unary_union([pocket, hole])
        pins = register_pins(outline, blocked, w, h)
        parts = halve(mesh, z_mid, pins, w, h)
    else:
        parts = [("", mesh)]

    arcs = marks[:-n_tap] if n_tap else marks
    info = dict(
        kind=kind, w=round(w, 2), h=round(h, 2), thick=thick, rise=rise,
        parts=[p or kind for p, _ in parts], pins=len(pins),
        part_thick=round(rise + (thick / 2.0 if split else thick), 2),
        assembled=round(2 * rise + thick if split else rise + thick + rise, 2),
        pocket=[round(pocket_w, 2), round(pocket_h, 2), round(depth, 2)],
        tag_mode=tag_mode, lines=measured,
        mark_stroke=round(narrowest(arcs), 2),
        tap_stroke=round(narrowest(marks[-n_tap:]), 2) if n_tap else None,
        pause_z=None if pause_z is None else round(pause_z, 2),
        volume=round(sum(m.volume for _, m in parts) / 1000.0, 2),
        watertight=all(m.is_watertight and m.is_winding_consistent for _, m in parts),
        font=Path(font).name,
    )
    info["total_z"] = round(max(m.bounds[1][2] for _, m in parts), 2)
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


def halve(mesh, z_mid, pins, w, h):
    """Cut the body at the glue joint and hand the front half the pins.

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
    hi = prisms([span], z_mid, mesh.bounds[1][2] + 1.0)

    studs = [rounded_rect(PIN["d"], PIN["d"], PIN["d"] / 2.0, *c) for c in pins]
    bores = [rounded_rect(PIN["d"] + 2 * PIN["clearance"], PIN["d"] + 2 * PIN["clearance"],
                          PIN["d"] / 2.0 + PIN["clearance"], *c) for c in pins]

    front = boolean("intersection", [mesh, *lo])
    if studs:
        front = boolean("union", [front, *prisms(studs, z_mid - 0.3, PIN["height"] + 0.3)])
    back = boolean("intersection", [mesh, *hi])
    if bores:
        back = boolean("difference",
                       [back, *prisms(bores, z_mid - 0.01, PIN["height"] + 0.16)])

    back.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0]))
    for part in (front, back):
        part.apply_translation((0.0, 0.0, -part.bounds[0][2]))
    return [("front", front), ("back", back)]
