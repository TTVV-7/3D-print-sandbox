"""World Drive merch: keychains and coasters.

    python3 worlddrive/designs.py

Draws the World Drive mark -- a blue globe, a yellow road swooping down over
it and round it like an orbit, a white car on the road -- as flat, printable
artwork, and sets it on keychains and coasters through src/logocard.py, which
already turns an SVG into a multi-colour inlaid part.

Four filaments, which is one AMS / a four-head printer exactly:

    body     navy     #0b1424   (the site's night sky)
    primary  blue     #2b7de0   (the globe)
    second   yellow   #ffd23f   (the road, "DRIVE")
    pattern  white    #ffffff   (the car, the lane dashes, "WORLD")

Everything is drawn in shapely and written out as plain filled SVG paths, so
the trace is exact: no strokes, no dashes, no fonts left for the reader.
"""
import sys
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.validation import make_valid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

import cards          # noqa: E402
import logocard       # noqa: E402
import render         # noqa: E402
import trace_text     # noqa: E402

NAVY, BLUE, YELLOW, WHITE = "#0b1424", "#2b7de0", "#ffd23f", "#ffffff"
FONT = ROOT / "src" / "fonts" / "RacingSansOne-Regular.ttf"
GAP = 1.3          # navy keyline between colours, in art units (mark is ~100 wide)


# --------------------------------------------------------------- drawing ---

def bezier(p, n=160):
    p = np.asarray(p, float)
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1]
            + 3 * (1 - t) * t ** 2 * p[2] + t ** 3 * p[3])


def ribbon(pts, w0, w1):
    """A band along `pts` whose width runs from w0 to w1 -- the road coming
    towards you in perspective."""
    pts = np.asarray(pts)
    w = np.linspace(w0, w1, len(pts))
    d = np.gradient(pts, axis=0)
    n = np.column_stack([-d[:, 1], d[:, 0]])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    left, right = pts + n * w[:, None] / 2, pts - n * w[:, None] / 2
    return Polygon(np.vstack([left, right[::-1]])).buffer(0)


def dashes(pts, w0, w1, on=0.55, period=9.0, thick=0.09, least=0.9, min_road=0.0):
    """Lane dashes down the middle of the road, scaled with its width.
    `thick` is the dash's half-width as a share of the road's width, never
    under `least`; no dashes where the road is narrower than `min_road`."""
    pts = np.asarray(pts)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    w = np.linspace(w0, w1, len(pts))
    out, pos = [], period * 0.6
    while pos < s[-1] - period * 0.3:
        i = min(np.searchsorted(s, pos), len(w) - 1)
        k = w[i] / w1                                    # perspective scale
        step = period * (0.5 + 0.5 * k)
        if w[i] < min_road:
            pos += step
            continue
        a, b = pos, min(pos + period * on * (0.5 + 0.5 * k), s[-1])
        sub = [np.interp(a, s, pts[:, 0]), np.interp(a, s, pts[:, 1])], \
              [np.interp(b, s, pts[:, 0]), np.interp(b, s, pts[:, 1])]
        mid = pts[(s >= a) & (s <= b)]
        line = np.vstack([sub[0], *mid, sub[1]]) if len(mid) else np.array(sub)
        out.append(LineString(line).buffer(max(least, w[i] * thick), cap_style=2))
        pos += step
    return unary_union(out)


def car(at, angle, scale=1.0):
    """A little car seen from above, nose along +x: white body, navy glass."""
    body = box(-6.5, -3.2, 6.5, 3.2).buffer(1.4)
    nose = Point(6.0, 0).buffer(3.6)
    body = unary_union([body, nose.intersection(box(5, -4.6, 9, 4.6))])
    glass = unary_union([
        Polygon([(1.2, -3.2), (3.8, -2.6), (3.8, 2.6), (1.2, 3.2)]),     # windscreen
        Polygon([(-5.2, -2.6), (-3.6, -3.0), (-3.6, 3.0), (-5.2, 2.6)]),  # rear window
    ])
    shell = body.difference(glass)
    shell = affinity.scale(shell, scale, scale, origin=(0, 0))
    shell = affinity.rotate(shell, angle, origin=(0, 0))
    return affinity.translate(shell, *at)


# Two drawings of the same mark.  "full" is for things where the mark ends up
# 80 mm or more across (the big coasters); "bold" is for keychains and the
# infill coasters' centre disc, where it is 30-45 mm across and every line has
# to be at least two passes of a 0.4 mm nozzle: fewer, fatter grid lines,
# wider keylines between the colours, bigger dashes only where the road is
# wide enough for them, and a bigger car.
DETAIL = {
    "full": dict(gap=1.3, grid=1.1, meridians=(0.42, 0.80), parallels=(-0.5, 0.0, 0.5),
                 dash=dict(period=9.0, thick=0.09, least=0.9), car=0.95, inset=1.4),
    "bold": dict(gap=2.2, grid=1.7, meridians=(0.55,), parallels=(-0.45, 0.2),
                 dash=dict(period=15.0, on=0.5, thick=0.12, least=1.7, min_road=10.0),
                 car=1.35, inset=2.0),
}


def mark(detail="full"):
    """{colour: geometry} for the World Drive mark, y up, about 100 x 100."""
    o = DETAIL[detail]
    gap = o["gap"]
    cx, cy, r = 48.0, 50.0, 34.0
    globe = Point(cx, cy).buffer(r, 256)

    # graticule: meridians and parallels, cut as navy lines
    grid = []
    for k in o["meridians"]:
        ring = affinity.scale(Point(0, 0).buffer(1, 256), r * k, r)
        grid.append(affinity.translate(ring.exterior, cx, cy).buffer(o["grid"]))
    grid.append(LineString([(cx, cy - r), (cx, cy + r)]).buffer(o["grid"]))
    for k in o["parallels"]:
        dy = r * k
        grid.append(LineString([(cx - r, cy + dy), (cx + r, cy + dy)]).buffer(o["grid"]))
    grid = affinity.rotate(unary_union(grid), -18, origin=(cx, cy)).intersection(globe)

    # the road: down from the top right, over the globe, round the bottom
    road_pts = np.vstack([
        bezier([(80, 99), (70, 88), (58, 72), (48, 58)], 80),
        bezier([(48, 58), (36, 40), (8, 34), (6, 20)], 80)[1:],
        bezier([(6, 20), (4, 6), (40, 0), (72, 10)], 80)[1:],
        bezier([(72, 10), (88, 15), (98, 24), (96, 34)], 60)[1:],
    ])
    road = ribbon(road_pts, 5.0, 15.0)
    lane = dashes(road_pts, 5.0, 15.0, **o["dash"]).intersection(road.buffer(-o["inset"]))

    # the car sits at the near end of the road
    t = np.argmin(np.linalg.norm(road_pts - np.array([86, 26]), axis=1))
    d = road_pts[min(t + 1, len(road_pts) - 1)] - road_pts[max(t - 1, 0)]
    ang = np.degrees(np.arctan2(d[1], d[0]))
    shell = car(road_pts[t], ang, o["car"])

    road_y = road.difference(lane.buffer(gap * 0.6)).difference(shell.buffer(gap))
    globe_b = globe.difference(grid).difference(road.buffer(gap)).difference(
        shell.buffer(gap))
    lane = lane.difference(shell.buffer(gap * 2.5))
    return clean({BLUE: globe_b, YELLOW: road_y, WHITE: unary_union([lane, shell])})


def clean(layers):
    """Valid polygons only, and specks too small to print dropped."""
    out = {}
    for k, g in layers.items():
        g = make_valid(g).buffer(0)
        polys = [p for p in getattr(g, "geoms", [g])
                 if p.geom_type == "Polygon" and p.area > 0.4]
        out[k] = unary_union(polys)
    return out


def text(s, height, at=(0, 0), font=FONT, tracking=0.02):
    """Outlines of `s`, cap height ~`height`, baseline-left at `at`."""
    shapes = trace_text.trace(s, str(font), tracking=tracking)
    g = unary_union([sh.buffer(0) for sh in shapes])
    k = height / cards.cap_per_em(str(font))
    g = affinity.scale(g, k, k, origin=(0, 0))
    return affinity.translate(g, at[0] - g.bounds[0], at[1])


def arc_text(s, radius, centre, height, top=True, font=FONT, tracking=0.06):
    """`s` set round a circle -- over the top reading left to right, or under
    the bottom reading left to right too."""
    letters, x = [], 0.0
    for ch in s:
        if ch == " ":
            x += height * 0.45
            letters.append(None)
            continue
        g = text(ch, height, font=font, tracking=0)
        w = g.bounds[2] - g.bounds[0]
        letters.append((g, x, w))
        x += w + height * tracking
    total = x - height * tracking
    out = []
    rr = radius if top else radius + height       # baseline radius
    for item in letters:
        if item is None:
            continue
        g, x0, w = item
        mid = x0 + w / 2 - total / 2                    # arc length from centre
        theta = mid / rr
        g = affinity.translate(g, -(g.bounds[0] + w / 2), 0)
        if top:
            g = affinity.translate(g, 0, rr)
            g = affinity.rotate(g, -theta, origin=(0, 0), use_radians=True)
        else:
            g = affinity.translate(g, 0, -rr)
            g = affinity.rotate(g, theta, origin=(0, 0), use_radians=True)
        out.append(make_valid(affinity.translate(g, *centre)).buffer(0))
    return unary_union(out)


def to_svg(layers, path, pad=2.0):
    """Write {colour: geometry} (y up) as filled SVG paths, painted in order."""
    allg = unary_union(list(layers.values()))
    x0, y0, x1, y1 = allg.bounds
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    H = y1 - y0

    def ring(c):
        pts = np.asarray(c.coords)
        return "M" + "L".join(f"{x - x0:.3f},{H - (y - y0):.3f}" for x, y in pts) + "Z"

    paths = []
    for colour, g in layers.items():
        for p in getattr(g, "geoms", [g]):
            if p.is_empty or p.geom_type != "Polygon":
                continue
            d = ring(p.exterior) + "".join(ring(i) for i in p.interiors)
            paths.append(f'<path fill="{colour}" fill-rule="evenodd" d="{d}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {x1 - x0:.3f} {H:.3f}">'
           + "".join(paths) + "</svg>")
    Path(path).write_text(svg)
    return svg


# --------------------------------------------------------------- designs ---

def wordmark_badge():
    """The mark on the left, WORLD over DRIVE on the right (keychain-sized,
    so the bold mark)."""
    m = mark("bold")
    x = 104
    w = text("WORLD", 30, (x, 52))
    d = text("DRIVE", 30, (x, 14))
    # Racing Sans One is already slanted; match the widths so it reads as a block
    k = (w.bounds[2] - w.bounds[0]) / (d.bounds[2] - d.bounds[0])
    d = affinity.scale(d, k, 1, origin=(x, 14))
    return clean({BLUE: m[BLUE], YELLOW: unary_union([m[YELLOW], d]),
                  WHITE: unary_union([m[WHITE], w])})


def coaster_badge():
    """A round badge: the mark in the middle, WORLD DRIVE over the top,
    worlddrive.app under the bottom, a yellow rim."""
    m = mark()
    c = (50.0, 50.0)
    # mark scaled into the middle
    allm = unary_union(list(m.values()))
    mx0, my0, mx1, my1 = allm.bounds
    s = 58 / max(mx1 - mx0, my1 - my0)
    mc = ((mx0 + mx1) / 2, (my0 + my1) / 2)

    def place(g):
        g = affinity.translate(g, c[0] - mc[0], c[1] - mc[1])
        return affinity.scale(g, s, s, origin=c)
    m = clean({k: place(v) for k, v in m.items()})
    top = arc_text("WORLD DRIVE", 37.5, c, 9.5, top=True, tracking=0.1)
    bottom = arc_text("worlddrive.app", 36.6, c, 7.6, top=False, tracking=0.07)
    rim = Point(*c).buffer(48.5, 256).difference(Point(*c).buffer(46.3, 256))
    stars = unary_union([Point(c[0] + 41 * np.cos(a), c[1] + 41 * np.sin(a)).buffer(1.6)
                         for a in np.radians([180 + 8, -8])])
    return clean({BLUE: m[BLUE],
                  YELLOW: unary_union([m[YELLOW], bottom.buffer(0), rim, stars]),
                  WHITE: unary_union([m[WHITE], top.buffer(0)])})


# ---------------------------------------------------------------- output ---

LIGHT = "#8cc4ff"      # the traced mark's continents and car glass (trace_mark.py)

# The relief keychain's heights over its 3 mm body, mm: the ocean lowest, its continents
# above it, the road lifted off the world, its lane dashes above the road, and the car above
# them.
RELIEF = dict(ocean=0.4, land=0.8, road=1.2, dashes=1.5, car=1.8)
GLASS = 0.4            # how deep the car's windows sit in its top


def relief_keychain(size=55.0, thick=3.0, border=2.0, label="wd_logo_keychain"):
    """The site's current mark as a keychain in steps: ocean, continents, road and car each a
    level higher (RELIEF). The pieces are trace_mark.py's (art/mark_logo_keychain.json). Three
    of them are inlays, as logocard makes them (ocean blue, continents light blue, road
    yellow); the car and the lane dashes are navy, the body's own colour, so they're blocks of
    the body standing up off the face, the car's windows set into its top in the continents'
    light blue. Returns
    ([part], info) like logocard.build. Printed back down: every step stands on the one
    under it, so nothing needs a support."""
    import json
    from shapely import wkt

    names = ("ocean", "land", "road", "car", "glass", "dashes")
    raw = json.loads((HERE / "art" / "mark_logo_keychain.json").read_text())
    pieces = [(name, wkt.loads(raw[name])) for name in names]
    placed, _, outline, _ = logocard.fit_art(pieces, size, border, "outline", True)
    p = dict(placed)
    ink = unary_union(list(p.values()))
    outline, hole, ring_got = logocard.keyring(outline, ink, "tab", "top-left", logocard.RING_D)
    body_2d = outline.difference(hole) if hole is not None else outline
    keep = outline.buffer(-0.3)
    off = hole.buffer(0.6) if hole is not None else Polygon()
    face = logocard.FACE

    body = cards.prisms([body_2d], 0.0, thick)[0]
    cutters, groups = [], []
    for slot, name in (("primary", "ocean"), ("pattern", "land"), ("secondary", "road")):
        polys = logocard.tidy(p[name].intersection(keep).difference(off))
        groups.append(dict(slot=slot, element="logo", face="front",
                           mesh=logocard.solid(polys, thick - face - 0.01, face + RELIEF[name] + 0.01)))
        cutters.append(logocard.solid(polys, thick - face, face + 1.0))
    body = cards.boolean("difference", [body, *cutters])

    # The car: a navy block on the face, its windows let into its top.
    car = logocard.tidy(p["car"].intersection(keep).difference(off))
    top = thick + RELIEF["car"]
    glass = logocard.tidy(p["glass"].intersection(unary_union(car).buffer(-0.3)))
    block = logocard.solid(car, thick - 0.01, RELIEF["car"] + 0.01)
    if glass:
        block = cards.boolean("difference", [block, logocard.solid(glass, top - GLASS, 1.0)])
        groups.append(dict(slot="pattern", element="logo", face="front",
                           mesh=logocard.solid(glass, top - GLASS - 0.01, GLASS + 0.01)))
    # The lane dashes: navy too, standing up out of the road.
    dashes = logocard.tidy(p["dashes"].intersection(keep).difference(off))
    if dashes:
        block = cards.boolean("union", [block, logocard.solid(dashes, thick - 0.01, RELIEF["dashes"] + 0.01)])
    body = cards.boolean("union", [body, block])
    groups.insert(0, dict(slot="body", element="body", face="body", mesh=body))
    part = logocard.finish(dict(name="", label=label, card=0, groups=groups, assembled=np.eye(4)))
    x0, y0, x1, y1 = body_2d.bounds
    finest = min(float(cards.finest(logocard.tidy(p[n].intersection(keep)))) for n in ("ocean", "land", "road"))
    info = dict(w=round(x1 - x0, 2), h=round(y1 - y0, 2), total_z=round(top, 2), ring=ring_got,
                nfc=None, slots=["body", "primary", "secondary", "pattern"], finest=round(finest, 2),
                art=[dict(slot="primary", hex=BLUE), dict(slot="secondary", hex=YELLOW),
                     dict(slot="pattern", hex=LIGHT)])
    return [part], info


NAMES = {NAVY: "Navy", BLUE: "Blue", YELLOW: "Yellow", WHITE: "White", LIGHT: "Light blue"}
MATERIAL = "PETG"      # copes with a hot mug better than PLA; change it in the slicer if you like


def filaments(palette):
    """A palette in cards.SLOTS order as cards.export_3mf_tools wants it: each colour a
    filament, so the slicer (Orca, Snapmaker's, PrusaSlicer) opens the file with every part
    already on its own extruder."""
    return [dict(hex=c, material=MATERIAL, name=NAMES.get(c, c)) for c in palette]


def export(parts, palette, row_w=None, **kw):
    """The parts as a 3MF in Bambu Studio's form (bambu3mf.py), so Snapmaker's slicer, Orca and
    Bambu Studio open it with every colour on its own extruder: 1 navy, 2 yellow, 3 blue,
    4 white (or the traced logo's light blue). A set laid out for one plate (row_w) goes two
    across."""
    import io
    import bambu3mf
    buf = io.BytesIO()
    bambu3mf.write(buf, bambu3mf.from_parts(parts, palette, cards.SLOTS), cols=2 if row_w else 4)
    return buf.getvalue()


PALETTE = (NAVY, BLUE, YELLOW, WHITE)
BODY = (NAVY,) + tuple(cards.COLOURS[1:])

DESIGNS = [
    # name, art, logocard.build kwargs
    ("wd_mark_keychain", "mark_bold",
     dict(size=45, backing="outline", border=2.0, ring="tab", ring_at="top-left",
          nfc=False, back="none")),
    ("wd_mark_keychain_nfc", "mark_bold",
     dict(size=50, backing="outline", border=2.0, ring="tab", ring_at="top-left",
          nfc=True, back="arcs", link="https://worlddrive.app", fit="halves")),
    ("wd_wordmark_keychain", "wordmark",
     dict(size=80, backing="rounded", border=3.0, ring="hole", ring_at="left",
          nfc=False, back="none")),
    ("wd_coaster_mark", "mark",
     dict(size=100, thick=4.0, backing="circle", border=8.0, ring="none",
          nfc=False, back="none")),
    # The site's current mark itself as the coaster (art/mark_logo.svg, traced from it by
    # trace_mark.py): die-cut to the globe, the road and the orbit ring, no disc. The globe
    # (its ocean, "primary", and its continents, "pattern") stands 1.2 mm above the road and
    # the navy, so it's what the mug sits on; 4.8 mm at its tallest, printed back down.
    ("wd_coaster_logo", "logo",
     dict(size=110, thick=3.6, backing="outline", border=2.5, ring="none",
          nfc=False, back="none", rises={"primary": 1.2, "pattern": 1.2})),
    ("wd_coaster_badge", "badge",
     dict(size=100, thick=4.0, backing="circle", border=1.0, ring="none",
          nfc=False, back="none")),
]


def main():
    art_dir, out_dir, prev_dir = HERE / "art", HERE / "stl", HERE / "previews"
    for d in (art_dir, out_dir, prev_dir):
        d.mkdir(exist_ok=True)
    arts = {"mark": mark(), "mark_bold": mark("bold"), "wordmark": wordmark_badge(),
            "badge": coaster_badge()}
    svgs = {k: to_svg(v, art_dir / f"{k}.svg") for k, v in arts.items()}
    # The current mark, already flat colours (trace_mark.py makes it from the site's logo).
    svgs["logo"] = (art_dir / "mark_logo.svg").read_text()

    sheet = []
    for name, art, kw in DESIGNS:
        parts, info = logocard.build(svgs[art], colours=BODY, label=name, **kw)
        palette = list(BODY)
        for r in info["art"]:
            palette[cards.SLOTS.index(r["slot"])] = r["hex"]
        (out_dir / f"{name}.3mf").write_bytes(export(parts, tuple(palette)))
        cards.plate(logocard.weld(parts)).export(out_dir / f"{name}.stl")
        # a two-half NFC card is shown glued up, not as its two plate halves
        moves = [p.get("assembled") for p in parts] if len(parts) > 1 else None
        mesh, cols = render.coloured(parts, palette, moves)
        wide = info["w"] / info["h"] > 1.6
        render.render(mesh, prev_dir / f"{name}.png", elev=58, azim=-90,
                      zoom=0.95 if wide else 1.3, colours=cols, bg=(236, 238, 242))
        sheet.append(prev_dir / f"{name}.png")
        print(f"{name}: {info['w']} x {info['h']} x {info['total_z']} mm, "
              f"{len(info['slots'])} colours, ring {info['ring']}, "
              f"chip {info['nfc']['d'] if info['nfc'] else 'none'}, "
              f"slots {[(r['slot'], r['hex']) for r in info['art']]}")

    # The relief keychain: the current mark in steps, built here rather than by logocard.
    parts, info = relief_keychain()
    name = parts[0]["label"]
    palette = list(BODY)
    for r in info["art"]:
        palette[cards.SLOTS.index(r["slot"])] = r["hex"]
    (out_dir / f"{name}.3mf").write_bytes(export(parts, tuple(palette)))
    cards.plate(logocard.weld(parts)).export(out_dir / f"{name}.stl")
    mesh, cols = render.coloured(parts, palette, None)
    render.render(mesh, prev_dir / f"{name}.png", elev=58, azim=-90, zoom=1.3, colours=cols,
                  bg=(236, 238, 242))
    render.render(mesh, prev_dir / f"{name}_side.png", elev=20, azim=-70, zoom=1.3, colours=cols,
                  bg=(236, 238, 242))
    sheet.append(prev_dir / f"{name}.png")
    print(f"{name}: {info['w']} x {info['h']} x {info['total_z']} mm, steps {RELIEF}, "
          f"ring {info['ring']}, finest {info['finest']} mm")

    from PIL import Image
    ims = [Image.open(p) for p in sheet]
    w, h = ims[0].size
    out = Image.new("RGB", (w * 3, h * -(-len(ims) // 3)), (236, 238, 242))
    for i, im in enumerate(ims):
        out.paste(im, ((i % 3) * w, (i // 3) * h))
    out.save(prev_dir / "all.png")


if __name__ == "__main__":
    main()
