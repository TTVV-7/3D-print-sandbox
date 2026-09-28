"""The NFC business card, remade: a company's logo *is* the card.

    parts, info = logocard.build(open("logo.svg").read())
    parts, info = logocard.build(png_bytes, size=80, ring="hole", ring_at="top-right")

Hand it the logo -- an SVG, or a PNG / JPEG / WebP -- and the card comes out
in the logo's own outline and the logo's own colours, with an NFC sticker
sealed inside it and a way onto a keyring.

**The shape.**  Every colour of the logo is traced and merged into one
silhouette, and the card is that silhouette grown by `border` mm of plain
body all round: a die-cut sticker's outline, in plastic.  Letters and marks
that stand apart are bridged together until the whole thing is one piece, and
the holes inside it -- the middle of an O -- are filled, so the card is solid
and there is room for the chip.  A wordmark too thin for that can sit on a
rounded rectangle or a disc instead (`backing`).

**The colours.**  Each colour in the logo is an inlay FACE mm deep in the
front, flush with the body, the way every other part in this repo does its
colour: the printer changes filament only in the last three layers.  A
four-head printer is one head for the body and three for the logo, so a logo
with more colours than that has its closest colours merged; one that matches
the body colour -- white lettering on a white card -- needs no inlay at all
and costs no head.  The colours reported back are the logo's own, so the app
can start the colour pickers on them.

**The keyring.**  A tab with a hole in it, standing off the outline at the
corner you pick, or a hole punched through the card itself in that corner,
kept clear of the artwork.  If there is no room for a hole clear of the logo
it becomes a tab rather than a hole through the logo.

**The chip.**  A round NTAG sticker in a pocket in the middle of the
thickness, at the roomiest point of the card, printed over: the print pauses
once, you drop the sticker in, and it is sealed for good (pettag's pocket,
exactly).  The back carries the contactless arcs right over it, so whoever
is holding the card knows where to put their phone -- or a QR code for the
same link, for phones that do not tap.

The parts are the same shape as cards.build()'s, so the plate, the 3MF, the
STL and the app's viewer all take them unchanged.
"""
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon
from shapely.ops import polylabel, unary_union

import cards
import pettag
import trace_image
import trace_svg

SAMPLE = Path(__file__).resolve().parent / "sample_logo.svg"

# Longest side of the finished card, tab aside.  A business card is 85 mm; a
# logo card reads as a card from about 60 and still fits a wallet at 85.
SIZE = 70.0
SIZE_MIN, SIZE_MAX = 30.0, 150.0

# Thick enough to seal a 0.5 mm sticker between two faces with solid plastic
# either side (pettag.chip_pocket needs 2.4 mm), and to feel like a card
# rather than a sticker.
THICK = 3.0

# Plain body round the logo.  Also what bridges the gaps: two marks closer
# than twice this come out joined without anything else being done.
BORDER = 2.0

FACE = cards.FACE
LAYER = pettag.LAYER

BACKINGS = ("outline", "rounded", "circle")
RINGS = ("tab", "hole", "none")
CORNERS = {
    "top-left": (-1.0, 1.0), "top": (0.0, 1.0), "top-right": (1.0, 1.0),
    "left": (-1.0, 0.0), "right": (1.0, 0.0),
    "bottom-left": (-1.0, -1.0), "bottom-right": (1.0, -1.0),
}
RING_D = 5.0             # a split ring's wire goes through 4; 5 is easy
RING_WALL = 2.4          # plastic round the hole, where the pull is
CLEAR = 0.8              # a hole keeps this far off the artwork
CORNER_IN = 5.0          # and sits no further than this past its plastic from the edge

# The most any colour of the logo stands off the face.
RISE_MAX = 3.0

# Colour.  Four heads on the printer: the body and up to three for the logo.
INLAYS = 3
INLAY_SLOTS = ("primary", "secondary", "pattern")     # by area, largest first
# A logo colour this close to the body colour (RGB, 0-255) is the body.
FOLD = 40.0

# Chips tried, largest first, when none is named.  A bigger coil reads from
# further off, so the card gets the biggest one it has room for.
CHIPS = (25.0, 20.0, 15.0, 12.0)
# The mark on the back, as a share of the chip it points at, and its ceiling.
MARK = 0.75
MARK_MAX = 16.0


def _rgb(hexc):
    return np.array([int(hexc[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)


def _flat(geom):
    if geom is None or geom.is_empty:
        return []
    return [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and g.area > 0]


def read_art(art, colours=INLAYS + 1, keep_background=False, report=None):
    """[(hex, geometry)] for whatever was handed in: SVG text, a path to an
    SVG, image bytes or an image data: URL.  Nothing at all is the sample.
    A background taken off it is noted in `report`."""
    kw = dict(keep_background=keep_background, report=report)
    if not art:
        return trace_svg.painted(SAMPLE.read_text(), **kw)
    if isinstance(art, str) and art.lstrip().startswith("<"):
        return trace_svg.painted(art, **kw)
    if isinstance(art, str) and art.startswith("data:image/svg"):
        import base64
        import urllib.parse
        head, _, body = art.partition(",")
        text = base64.b64decode(body).decode() if ";base64" in head else urllib.parse.unquote(body)
        return trace_svg.painted(text, **kw)
    if isinstance(art, str) and not art.startswith("data:") and Path(art).is_file():
        if art.lower().endswith(".svg"):
            return trace_svg.painted(Path(art).read_text(), **kw)
        art = Path(art).read_bytes()
    return trace_image.painted(art, colours=colours, **kw)


INK, PAPER = "#0c1a2e", "#ffffff"


def body_for(regions, background):
    """The body colour a logo would choose for itself: the background it was
    drawn on, if it came on one; otherwise white, unless the logo is mostly
    light, in which case ink -- a white logo on a white card is a blank."""
    if background:
        return background
    big = max(regions, key=lambda r: r[1].area)[0]
    r, g, b = _rgb(big) / 255.0
    return INK if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.75 else PAPER


# Anything of an inlay narrower than twice this, or smaller than SPECK mm^2,
# is below what a nozzle can put down: slivers where two traced colours meet,
# the anti-aliased crumbs of a raster, a counter too small to stay open.
SLIVER = 0.12
SPECK = 0.3


def tidy(g):
    """An inlay's polygons with the unprintable crumbs taken off it."""
    g = g.buffer(-SLIVER, quad_segs=8).buffer(SLIVER, quad_segs=8)
    out = []
    for p in _flat(g):
        if p.area < SPECK:
            continue
        holes = [r for r in p.interiors if Polygon(r).area >= SPECK]
        out.append(Polygon(p.exterior, holes))
    return out


def sort_colours(regions, body_hex, most=INLAYS):
    """Which logo colour goes in which slot.

    Returns (inlays, folded): `inlays` is [(slot, hex, geometry)], largest
    first; `folded` the logo colours that became the body.  Colours near the
    body colour fold into it; past `most`, the two closest colours left are
    merged -- into the larger one's colour -- until they fit.
    """
    body = _rgb(body_hex)
    keep, folded = [], []
    for hexc, g in regions:
        (folded if np.linalg.norm(_rgb(hexc) - body) < FOLD else keep).append([hexc, g])
    while len(keep) > most:
        best = None
        for i in range(len(keep)):
            for j in range(i + 1, len(keep)):
                d = np.linalg.norm(_rgb(keep[i][0]) - _rgb(keep[j][0]))
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        big, small = (i, j) if keep[i][1].area >= keep[j][1].area else (j, i)
        keep[big][1] = keep[big][1].union(keep[small][1])
        del keep[small]
    keep.sort(key=lambda r: -r[1].area)
    return ([(INLAY_SLOTS[i], h, g) for i, (h, g) in enumerate(keep)],
            [h for h, _ in folded])


def silhouette(art, border, backing, fill_holes=True):
    """The card's outline round `art` (the logo's union, in mm).  Returns
    (outline, bridged): how far apart pieces were bridged, in mm, 0 if they
    joined on their own."""
    if backing == "rounded":
        x0, y0, x1, y1 = art.bounds
        w, h = x1 - x0 + 2 * border, y1 - y0 + 2 * border
        return cards.rounded_rect(w, h, min(w, h) * 0.18, (x0 + x1) / 2, (y0 + y1) / 2), 0.0
    if backing == "circle":
        from shapely import minimum_bounding_circle
        c = minimum_bounding_circle(art)
        centre, r = c.centroid, np.sqrt(c.area / np.pi)
        return Point(centre.x, centre.y).buffer(r + border, quad_segs=64), 0.0
    if backing != "outline":
        raise ValueError(f"no such backing: {backing} -- {', '.join(BACKINGS)}")

    def fill(g):
        return unary_union([Polygon(p.exterior) for p in _flat(g)]) if fill_holes else g

    # Grow, then close gaps a little wider each time, until it is one piece.
    base = art.buffer(border, quad_segs=16)
    for gap in (0.0, 1.0, 2.0, 3.5, 5.0, 8.0, 12.0):
        shape = base if not gap else base.buffer(gap, quad_segs=16).buffer(-gap, quad_segs=16)
        shape = fill(shape)
        if len(_flat(shape)) == 1:
            # Round off any corner the grow left sharp -- a point snaps --
            # unless that would part a thin neck.
            smooth = shape.buffer(-0.6, quad_segs=16).buffer(0.6, quad_segs=16)
            return (smooth if len(_flat(smooth)) == 1 else _flat(shape)[0]), gap
    return fill(base.convex_hull), 99.0


def mirror(g):
    """Turned over left to right about the card's centre line: where a shape
    drawn to be read from behind lands in the card's own coordinates."""
    return affinity.scale(g, -1, 1, origin=(0, 0))


def fit_art(regions, size, border, backing, fill_holes, both=False):
    """Scale the logo so the finished card's longest side is `size` mm.
    Returns (regions in mm centred on the origin, outline, bridged).

    With `both`, the outline is cut round the logo *and* its mirror image,
    so the logo on the back -- the right way round from behind -- fits the
    card as well as the front one does.  A symmetric logo loses nothing."""
    every = unary_union([g for _, g in regions])
    x0, y0, x1, y1 = every.bounds
    cx, cy, long = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0)
    target = max(4.0, size - 2 * border)
    for _ in range(4):
        k = target / long
        place = lambda g: affinity.scale(affinity.translate(g, -cx, -cy), k, k, origin=(0, 0))
        art = place(every)
        outline, bridged = silhouette(unary_union([art, mirror(art)]) if both else art,
                                      border, backing, fill_holes)
        bx0, by0, bx1, by1 = outline.bounds
        got = max(bx1 - bx0, by1 - by0)
        if abs(got - size) < 0.05:
            break
        target *= size / got
    return [(h, place(g)) for h, g in regions], art, outline, bridged


def grow_end(outline, towards, by):
    """A rounded rectangle `by` mm longer at the end `towards` points at --
    the end along its long side, for a corner."""
    x0, y0, x1, y1 = outline.bounds
    dx, dy = towards
    if dx and (x1 - x0 >= y1 - y0 or not dy):
        x0, x1 = (x0 - by, x1) if dx < 0 else (x0, x1 + by)
    else:
        y0, y1 = (y0 - by, y1) if dy < 0 else (y0, y1 + by)
    w, h = x1 - x0, y1 - y0
    return cards.rounded_rect(w, h, min(w, h) * 0.18, (x0 + x1) / 2, (y0 + y1) / 2)


def keyring(outline, art, how, where, d):
    """(outline with its tab, the hole, what actually went on) for a keyring
    hole at corner `where`: a tab standing off the outline, or a hole in the
    card clear of the artwork -- which becomes a tab when there is no room."""
    if how == "none" or d <= 0.5:
        return outline, None, "none"
    v = np.array(CORNERS[where])
    v = v / np.linalg.norm(v)
    r_hole, r_keep = d / 2.0, d / 2.0 + RING_WALL
    if how == "hole":
        room = outline.buffer(-r_keep, quad_segs=16).difference(
            art.buffer(r_hole + CLEAR, quad_segs=16))
        pts = [c for p in _flat(room) for c in p.exterior.coords]
        # It has to be *in the corner*: no further in from the card's edge
        # that way than the plastic round it plus a few millimetres.  A gap
        # in the middle of the logo is room, but not a corner.
        edge = max(c[0] * v[0] + c[1] * v[1] for c in outline.exterior.coords)
        if pts:
            best = max(pts, key=lambda c: c[0] * v[0] + c[1] * v[1])
            if best[0] * v[0] + best[1] * v[1] >= edge - r_keep - CORNER_IN:
                return outline, Point(best).buffer(r_hole, quad_segs=32), "hole"
    # A tab: a disc on the outline's furthest point that way, sunk in so the
    # hole's inner rim is a millimetre inside the body, moved on out if that
    # would cut into the logo.
    pts = np.array(outline.exterior.coords)
    tip = pts[np.argmax(pts @ v)]
    step = r_hole - 1.0
    while True:
        centre = tip + v * step
        hole = Point(centre).buffer(r_hole, quad_segs=32)
        if not hole.intersects(art.buffer(CLEAR)) or step > r_keep + 6:
            break
        step += 0.25
    disc = Point(centre).buffer(r_keep, quad_segs=32)
    grown = unary_union([outline, disc]).buffer(1.2, quad_segs=16).buffer(-1.2, quad_segs=16)
    return grown, hole, "tab" if how == "tab" else "tab (no room for a hole clear of the logo)"


def build(art=None, size=SIZE, thick=THICK, border=BORDER, backing="outline",
          fill_holes=True, ring="tab", ring_at="top-left", ring_d=RING_D,
          colours=cards.COLOURS, max_colours=INLAYS, keep_background=False,
          rise=0.0, nfc=True, chip_d=None, chip_t=pettag.CHIP_T,
          back="arcs", link="", both=False, rises=None, label=""):
    """One logo card, as printable parts plus the numbers worth knowing.

    Returns ([part], info) in cards.build()'s shape.  info["art"] lists the
    logo's colours and the slot each went to, so a front end can start its
    colour pickers on them.

    `both` puts the logo on the back as well, reading the right way round
    when the card is turned over, in the same colours; the back then has no
    room for the tap mark or a QR code, and goes without.

    `rises` gives each logo colour its own height off the face, by slot --
    {"primary": 1.2, "secondary": 0.4} -- so a logo can be stepped: the
    lettering standing above its field, the field above the card.  A slot
    it leaves out stands at `rise`.
    """
    if backing not in BACKINGS:
        raise ValueError(f"no such backing: {backing} -- {', '.join(BACKINGS)}")
    if ring not in RINGS:
        raise ValueError(f"no such keyring fitting: {ring} -- {', '.join(RINGS)}")
    if ring_at not in CORNERS:
        raise ValueError(f"no such corner: {ring_at} -- {', '.join(CORNERS)}")
    if back not in ("arcs", "qr", "none"):
        raise ValueError(f"no such back: {back} -- arcs, qr or none")
    size = min(SIZE_MAX, max(SIZE_MIN, float(size)))
    thick = max(2.0, float(thick))
    border = max(0.0, float(border))
    rise = max(0.0, float(rise))
    rises = {k: min(RISE_MAX, max(0.0, float(v))) for k, v in (rises or {}).items()
             if k in INLAY_SLOTS}
    max_colours = min(INLAYS, max(1, int(max_colours)))
    link = (link or "").strip()

    seen = {}
    regions = read_art(art, colours=max_colours + 1, keep_background=keep_background,
                       report=seen)
    # The sample is drawn to sit on ink, the colour the page starts in.
    suggest = INK if not art else body_for(regions, seen.get("background"))
    regions, art_2d, outline, bridged = fit_art(regions, size, border, backing, fill_holes,
                                                both)
    # How far from symmetric the logo is: past a few percent, a two-sided
    # card's outline is visibly wider than the logo's own.
    widened = both and art_2d.symmetric_difference(mirror(art_2d)).area > 0.05 * art_2d.area
    inlays, folded = sort_colours(regions, colours[0], max_colours)
    # The hole keeps clear of what shows: the inlays.  A part of the logo in
    # the card's own colour is the card, and a hole may go through it.
    ink = unary_union([g for _, _, g in inlays]) if inlays else Polygon()
    if both:
        ink = unary_union([ink, mirror(ink)])
    outline, hole, ring_got = keyring(outline, ink, ring, ring_at, float(ring_d))
    if ring == "hole" and ring_got != "hole" and backing == "rounded":
        # A rectangle with no room in its corner grows at that end until
        # there is: a keyring tag's shape, rather than a tab off a card.
        outline = grow_end(outline, CORNERS[ring_at], float(ring_d) + 2 * RING_WALL)
        outline, hole, ring_got = keyring(outline, ink, ring, ring_at, float(ring_d))
    body_2d = outline.difference(hole) if hole is not None else outline

    # The front: each logo colour, clipped to the card and kept off the hole.
    # Pockets go a little past the face so the cut is clean; the inlays sit a
    # hundredth into the floor so the parts overlap rather than kiss.
    keep_off = hole.buffer(0.6) if hole is not None else None
    body = cards.prisms([body_2d], 0.0, thick)[0]
    cutters, groups_ = [], []
    report = []
    back_logo = False
    for slot, hexc, g in inlays:
        g = g.intersection(outline.buffer(-0.3))
        if keep_off is not None:
            g = g.difference(keep_off)
        polys = tidy(g)
        if not polys:
            continue
        up = rises.get(slot, rise)
        if up > 0:
            mesh = pettag.solid(polys, thick - FACE - 0.01, FACE + up + 0.01)
        else:
            mesh = pettag.solid(polys, thick - FACE - 0.01, FACE + 0.01)
        cutters.append(pettag.solid(polys, thick - FACE, FACE + 1.0))
        groups_.append(dict(slot=slot, element="logo", face="front", mesh=mesh))
        report.append(dict(slot=slot, hex=hexc, area=round(sum(p.area for p in polys), 1),
                           detail=round(float(cards.finest(polys)), 2), rise=round(up, 2)))
        if both:
            # The same colour on the back, turned over.  Always flush: the
            # back is the face on the bed, and relief there would need
            # supports.  Same slots, so a second side costs no extra head.
            under = [mirror(p) for p in polys]
            cutters.append(pettag.solid(under, -1.0, FACE + 1.0))
            groups_.append(dict(slot=slot, element="logo", face="back",
                                mesh=pettag.solid(under, 0.0, FACE + 0.01)))
            back_logo = True

    # The chip, at the roomiest point of the card, clear of the ring.
    chip = None
    if nfc:
        keep = [hole.buffer(RING_WALL)] if hole is not None else []
        tries = [float(chip_d)] if chip_d else list(CHIPS)
        for i, d in enumerate(tries):
            try:
                pocket, z0, z1 = pettag.chip_pocket(body_2d, keep, d, float(chip_t), thick)
                chip_d = d
                break
            except ValueError as exc:
                if "too thin" in str(exc) or i == len(tries) - 1:
                    hint = ("" if backing != "outline" else
                            " -- or put a rounded rectangle or a disc behind the logo")
                    raise ValueError(str(exc).replace("tag", "card") + hint) from None
        cutters.append(cards.prisms([pocket], z0, z1 - z0)[0])
        uri = link
        chip = dict(d=float(chip_d), t=float(chip_t),
                    pocket=round(2 * (float(chip_d) / 2 + pettag.CHIP_SLACK), 2),
                    z0=round(z0, 2), z1=round(z1, 2),
                    pause_z=round(z1, 2), resume_z=round(z1 + LAYER, 2),
                    centre=[round(pocket.centroid.x, 2), round(pocket.centroid.y, 2)],
                    uri=uri, bytes=cards_ndef(uri) if uri else None,
                    fits=bool(uri) and cards_ndef(uri) <= pettag.NTAG213)

    # The back is read turned over left to right, so whatever goes on it is
    # drawn as seen from behind and then mirrored into the card's coordinates.
    back_polys, qr = [], None
    mark_slot = inlays[0][0] if inlays else "primary"
    if back_logo:
        pass                    # the back is the logo's; nothing goes over it
    elif back == "qr" and link:
        rows = cards.qr_matrix(link)
        n = len(rows) + 2 * cards.QR_QUIET
        room = body_2d.buffer(-1.5, quad_segs=16)
        if hole is not None:
            room = room.difference(hole.buffer(RING_WALL))
        room = max(_flat(room), key=lambda p: p.area, default=None)
        if room is not None:
            c = polylabel(room, tolerance=0.1)
            module = 2 * room.exterior.distance(c) / np.sqrt(2.0) / n
            if module >= cards.QR_MIN_MODULE:
                back_polys = [affinity.scale(affinity.translate(p, c.x, c.y), -1, 1,
                                             origin=(c.x, 0))
                              for p in cards.qr_polys(rows, module)]
                qr = dict(modules=len(rows), module=round(module, 2),
                          size=round(module * len(rows), 2))
    elif back == "arcs" and chip:
        # Right behind the chip: from the back, the chip is at -x.
        cx, cy = chip["centre"]
        back_polys = [affinity.scale(affinity.translate(p, -cx, cy), -1, 1, origin=(0, 0))
                      for p in cards.contactless(min(MARK_MAX, chip["d"] * MARK))]
    if back_polys:
        back_polys = _flat(unary_union(back_polys).intersection(body_2d.buffer(-0.8)))
    if back_polys:
        cutters.append(pettag.solid(back_polys, -1.0, FACE + 1.0))
        groups_.append(dict(slot=mark_slot, element="qr" if back == "qr" else "arcs",
                            face="back", mesh=pettag.solid(back_polys, 0.0, FACE + 0.01)))

    if cutters:
        body = cards.boolean("difference", [body, *cutters])
    groups_.insert(0, dict(slot="body", element="body", face="body", mesh=body))

    part = dict(name="", label=label, card=0, groups=groups_, assembled=np.eye(4))
    part["slots"] = cards.slot_meshes(part)
    solids = [part["slots"][s] for s in cards.SLOTS if s in part["slots"]]
    part["mesh"] = solids[0] if len(solids) == 1 else cards.boolean("union", solids)

    x0, y0, x1, y1 = body_2d.bounds
    detail = min((r["detail"] for r in report), default=0.0)
    thin = []
    if report and detail < cards.MIN_STROKE:
        thin.append("logo detail")
    if back == "qr" and link and not qr:
        thin.append("qr")
    colour_slots = sorted({g["slot"] for g in groups_}, key=cards.SLOTS.index)
    total = float(part["mesh"].bounds[1][2])
    bands = [[0.0, round(FACE, 2)]] if back_polys or back_logo else []
    bands.append([round(thick - FACE, 2), round(total, 2)])
    info = dict(
        kind="card", label=label, front_up=True,
        w=round(x1 - x0, 2), h=round(y1 - y0, 2), thick=round(thick, 2),
        rise=round(max([r["rise"] for r in report] or [0.0]), 2),
        stepped=len({r["rise"] for r in report}) > 1,
        total_z=round(total, 2), size=round(size, 1),
        border=round(border, 2), backing=backing, bridged=bridged,
        both=back_logo, widened=bool(widened and back_logo),
        art=report, folded=folded, body=colours[0], suggest_body=suggest,
        source="svg" if (not art or (isinstance(art, str) and (art.lstrip().startswith("<")
                         or art.startswith("data:image/svg") or art.lower().endswith(".svg"))))
        else "image",
        sample=not art,
        ring=ring_got, ring_d=float(ring_d) if hole is not None else None,
        ring_at=ring_at if hole is not None else None,
        hole=[round(hole.centroid.x, 3), round(hole.centroid.y, 3), float(ring_d)]
        if hole is not None else None,
        back="logo" if back_logo else back if back_polys else "none", qr=qr, link=link,
        stroke=round(float(detail), 2), nozzle=cards.nozzle_for(detail) if report else None,
        slots=colour_slots, part_slots={"card": colour_slots}, parts=["card"], pins=0,
        part_thick=round(total, 2), assembled=round(total, 2),
        pocket=[0.0, 0.0, 0.0], tag_mode="none", joint=None, tag=[0, 0, 0],
        colour_bands=bands, colour_z=round(FACE, 2),
        volume=round(part["mesh"].volume / 1000.0, 2),
        watertight=part["mesh"].is_watertight and part["mesh"].is_winding_consistent,
        thin=thin, face=FACE, chamfer=0.0, layout=None, look=None,
        nfc=chip, pause_z=chip["pause_z"] if chip else None,
    )
    return [part], info


PREFIXES = ("https://www.", "http://www.", "https://", "http://", "tel:", "mailto:")


def cards_ndef(uri):
    """Bytes a one-record NDEF URI message takes on the chip: the TLV
    wrapper, the record header, a one-byte code for a common prefix, the rest
    and the terminator -- the same sum the page does for the fob's link."""
    rest = next((uri[len(p):] for p in PREFIXES if uri.startswith(p)), uri)
    return 8 + len(rest.encode())


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logo", nargs="?", help="an SVG, PNG, JPEG or WebP (default: the sample)")
    ap.add_argument("-o", "--out", default="logo_card.3mf", help=".3mf or .stl")
    ap.add_argument("--size", type=float, default=SIZE)
    ap.add_argument("--border", type=float, default=BORDER)
    ap.add_argument("--backing", choices=BACKINGS, default="outline")
    ap.add_argument("--ring", choices=RINGS, default="tab")
    ap.add_argument("--ring-at", choices=list(CORNERS), default="top-left")
    ap.add_argument("--body", default="#f5f2ec", help="body colour, #rrggbb")
    ap.add_argument("--link", default="")
    ap.add_argument("--back", choices=("arcs", "qr", "none"), default="arcs")
    ap.add_argument("--no-nfc", action="store_true")
    ap.add_argument("--both", action="store_true", help="the logo on the back too")
    ap.add_argument("--rises", default="", help="each logo colour's height, largest colour "
                    "first, in mm: 0,1.2 steps the second colour up 1.2 mm")
    a = ap.parse_args()
    body = (a.body,) + tuple(cards.COLOURS[1:])
    parts, info = build(a.logo, size=a.size, border=a.border, backing=a.backing,
                        ring=a.ring, ring_at=a.ring_at, colours=body, link=a.link,
                        back=a.back, nfc=not a.no_nfc, both=a.both,
                        rises=dict(zip(INLAY_SLOTS, map(float, filter(None,
                                                            a.rises.split(",")))))
                        if a.rises else None)
    palette = list(body)
    for r in info["art"]:
        palette[cards.SLOTS.index(r["slot"])] = r["hex"]
    if a.out.endswith(".stl"):
        cards.plate(parts).export(a.out)
    else:
        Path(a.out).write_bytes(cards.export_3mf(parts, tuple(palette)))
    print(f"{a.out}: {info['w']} x {info['h']} x {info['total_z']} mm, "
          f"{len(info['slots'])} colours, ring {info['ring']}, "
          f"chip {info['nfc']['d'] if info['nfc'] else 'none'}", file=sys.stderr)
