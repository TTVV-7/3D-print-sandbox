"""Open-top "infill" coasters: a solid base, a rim, and a pattern of thin
walls standing on it with nothing on top, so the pattern is the coaster.

    python3 worlddrive/infill_coasters.py

The look is usually got in the slicer by printing a coaster with no top
layers so its infill shows.  Here the walls are modelled instead, which
means it prints the same in any slicer with default settings, the pattern is
chosen rather than whatever the slicer's infill happens to be, and the walls
can be a different colour from the base: one filament change, at the top of
the base.

Four patterns make the set:

    honeycomb  hexagons, the classic
    gyroid     a slice through a gyroid -- the slicer infill everyone likes
    topo       contour lines of a made-up landscape, a map you could drive
    globe      the meridians and parallels of a globe seen face on

Each comes plain or with the World Drive mark on a solid disc in the middle.
"""
import sys
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import linemerge, unary_union

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

import cards       # noqa: E402
import render      # noqa: E402
import designs     # noqa: E402
import logocard    # noqa: E402

D = 100.0          # coaster diameter
BASE = 0.8         # solid floor: four 0.2 mm layers
HEIGHT = 3.2       # overall; the walls stand 2.4 mm proud of the floor (about 14 g, 16 with the logo)
RIM = 2.4          # rim width
WALL = 0.9         # pattern wall: two lines of a 0.4 mm nozzle
MIN_GAP = 1.2      # walls closer than this are merged into one solid band
MEDAL = 22.0       # radius of the solid centre disc on the branded ones
INLAY = 0.6        # depth of the logo's colours in that disc
CIRCLE = 32        # quarter-circle segments: 128 points round the rim
TOLERANCE = 0.05   # mm a simplified curve may stray from the true one (a line is 0.4)

R = D / 2
R_IN = R - RIM


# ------------------------------------------------------------- patterns ---

def contours(f, extent, level=0.0, n=240):
    """Marching squares: the curves where f(x, y) == level, as shapely lines."""
    xs = np.linspace(-extent, extent, n)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    F = f(X, Y) - level
    hi = F > 0
    case = (hi[:-1, :-1] * 1 | hi[1:, :-1] * 2 | hi[1:, 1:] * 4 | hi[:-1, 1:] * 8)
    table = {1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)], 5: [(3, 0), (1, 2)],
             6: [(0, 2)], 7: [(3, 2)], 8: [(2, 3)], 9: [(0, 2)], 10: [(0, 1), (2, 3)],
             11: [(1, 2)], 12: [(1, 3)], 13: [(0, 1)], 14: [(3, 0)]}

    def edge(i, j, e):
        a, b = [((i, j), (i + 1, j)), ((i + 1, j), (i + 1, j + 1)),
                ((i + 1, j + 1), (i, j + 1)), ((i, j + 1), (i, j))][e]
        fa, fb = F[a], F[b]
        t = fa / (fa - fb)
        x = xs[a[0]] + (xs[b[0]] - xs[a[0]]) * t
        y = xs[a[1]] + (xs[b[1]] - xs[a[1]]) * t
        return (round(float(x), 6), round(float(y), 6))

    segs = []
    for i, j in zip(*np.nonzero((case > 0) & (case < 15))):
        for e0, e1 in table[int(case[i, j])]:
            segs.append((edge(i, j, e0), edge(i, j, e1)))
    return linemerge(MultiLineString(segs))


def honeycomb(cell=10.0):
    """Hexagons `cell` mm across the flats."""
    a = cell / np.sqrt(3)                       # circumradius
    lines = []
    for i in range(-int(R / (1.5 * a)) - 2, int(R / (1.5 * a)) + 3):
        for j in range(-int(R / cell) - 2, int(R / cell) + 3):
            cx, cy = 1.5 * a * i, cell * (j + 0.5 * (i % 2))
            pts = [(cx + a * np.cos(t), cy + a * np.sin(t))
                   for t in np.radians(np.arange(0, 361, 60))]
            lines.append(LineString(pts))
    return unary_union(lines)


def gyroid(period=16.0, z=0.8):
    """The z-slice of sin x cos y + sin y cos z + sin z cos x = 0."""
    k = 2 * np.pi / period
    return contours(lambda x, y: np.sin(k * x) * np.cos(k * y)
                    + np.sin(k * y) * np.cos(z) + np.sin(z) * np.cos(k * x), R + 2)


def topo(seed=259, sigma=(16, 26), hills=7, closest=2.4):
    """Contour lines of a made-up landscape of rounded hills and hollows.

    The contour step is worked out from the steepest slope, so the closest
    two lines anywhere are `closest` mm apart, centre to centre: a 0.9 mm
    wall and a 1.5 mm gap.  The seed and hill sizes were picked from a few
    hundred by searching for landscapes with at least three hills or hollows
    on the face whose slopes are still even, so the lines never bunch and
    the biggest open pocket is about 12 mm."""
    rng = np.random.default_rng(seed)
    bumps = [(rng.uniform(-45, 45), rng.uniform(-45, 45), rng.uniform(*sigma),
              rng.choice([-1, 1]) * rng.uniform(0.6, 1.0)) for _ in range(hills)]

    def f(x, y):
        h = 0 * x
        for hx, hy, s, amp in bumps:
            h = h + amp * np.exp(-((x - hx) ** 2 + (y - hy) ** 2) / (2 * s * s))
        return h

    xs = np.linspace(-R_IN, R_IN, 240)
    X, Y = np.meshgrid(xs, xs)
    h = f(X, Y)
    gy, gx = np.gradient(h, xs, xs)
    inside = X ** 2 + Y ** 2 < R_IN ** 2
    step = closest * np.hypot(gx, gy)[inside].max()
    lo, hi = h[inside].min(), h[inside].max()
    return unary_union([contours(f, R + 2, lv)
                        for lv in np.arange(lo + step / 2, hi, step)])


def globe(lat_step=20, lon_step=22.5, tilt=-18):
    """A globe's graticule seen face on, tilted like the logo's."""
    r = R_IN + 1
    lines = []
    for lat in np.arange(-90 + lat_step, 90, lat_step):
        y, w = r * np.sin(np.radians(lat)), r * np.cos(np.radians(lat))
        lines.append(LineString([(-w, y), (w, y)]))
    t = np.radians(np.linspace(-90, 90, 120))
    for lon in np.arange(-90 + lon_step, 90, lon_step):
        s = np.sin(np.radians(lon))
        lines.append(LineString(np.column_stack([r * np.cos(t) * s, r * np.sin(t)])))
    return affinity.rotate(unary_union(lines), tilt, origin=(0, 0))


PATTERNS = {"honeycomb": honeycomb, "gyroid": gyroid, "topo": topo, "globe": globe}


# ---------------------------------------------------------------- build ---

def coaster(pattern, branded=False):
    """One coaster as a cards-style part: {"slots": {slot: mesh}, ...}.

    Slots: body = the floor (and the centre disc's face), pattern = the walls
    (and the logo's road), primary = the globe, secondary = the car."""
    # Few points, the same shapes: every point is G-code on every layer. Circles get 128
    # (each flat 0.006 mm deep), the walls' corners are sharp (one point, not a dozen
    # rounding it), and the curves keep only what's more than TOLERANCE off the line.
    disc = Point(0, 0).buffer(R, CIRCLE)
    inner = Point(0, 0).buffer(R_IN, CIRCLE)
    lines = PATTERNS[pattern]().simplify(TOLERANCE)
    walls = lines.buffer(WALL / 2, join_style="mitre", cap_style="flat", mitre_limit=3.0)
    # a slot narrower than about three nozzle widths prints as a smear, not a
    # gap: close it, so where lines bunch (the topo's steep slopes, the
    # globe's edge) they read as one clean band instead
    walls = walls.buffer(MIN_GAP / 2, join_style="mitre", mitre_limit=3.0).buffer(
        -MIN_GAP / 2, join_style="mitre", mitre_limit=3.0)
    walls = walls.intersection(inner).simplify(TOLERANCE / 2)
    keep = [disc.difference(inner), walls]
    if branded:
        medal = Point(0, 0).buffer(MEDAL, CIRCLE)
        keep[1] = walls.difference(medal.buffer(1.6))   # an open moat round it
        keep.append(medal)
    walls = unary_union(keep)

    by_slot = {"body": [disc], "pattern": [], "primary": [], "secondary": []}
    layers = [("body", [disc], 0.0, BASE)]
    top = HEIGHT - (INLAY if branded else 0.0)
    layers.append(("pattern", [walls], BASE, top - BASE))
    if branded:
        m = designs.mark("bold")          # every line two nozzle passes wide
        allm = unary_union(list(m.values()))
        x0, y0, x1, y1 = allm.bounds
        s = 2 * (MEDAL - 2.2) / max(x1 - x0, y1 - y0)
        c = ((x0 + x1) / 2, (y0 + y1) / 2)
        m = {k: affinity.scale(affinity.translate(v, -c[0], -c[1]), s, s, origin=(0, 0)).simplify(TOLERANCE)
             for k, v in m.items()}
        face = Point(0, 0).buffer(MEDAL, CIRCLE)
        art = unary_union(list(m.values()))
        layers.append(("body", [face.difference(art)], top, INLAY))
        layers.append(("primary", [m[designs.BLUE]], top, INLAY))
        layers.append(("pattern", [m[designs.YELLOW]], top, INLAY))
        layers.append(("secondary", [m[designs.WHITE]], top, INLAY))

    meshes = {k: [] for k in by_slot}
    for slot, geoms, z0, t in layers:
        polys = []
        for g in geoms:
            polys += logocard.tidy(g)       # slivers and specks off; valid rings
        meshes[slot] += cards.prisms(polys, z0, t)
    slots = {k: cards.trimesh.util.concatenate(v) for k, v in meshes.items() if v}
    name = f"wd_infill_{pattern}" + ("_logo" if branded else "")
    mesh = cards.trimesh.util.concatenate(list(slots.values()))
    return {"name": name, "label": "", "slots": slots, "mesh": mesh}


SETS = {
    # the walls in yellow on a navy floor; the centre disc's face is navy too
    "night": (designs.NAVY, designs.YELLOW, designs.BLUE, designs.WHITE),
}


def main():
    out_dir, prev_dir = HERE / "stl", HERE / "previews"
    palette = SETS["night"]
    sheet = []
    parts_by = {}
    for branded in (False, True):
        for pattern in PATTERNS:
            part = coaster(pattern, branded)
            parts_by[part["name"]] = part
            (out_dir / f"{part['name']}.3mf").write_bytes(designs.export([part], palette))
            mesh = cards.boolean("union", list(part["slots"].values()))
            mesh.export(out_dir / f"{part['name']}.stl")
            m, cols = render.coloured([part], palette)
            png = prev_dir / f"{part['name']}.png"
            render.render(m, png, elev=55, azim=-90, zoom=1.25, colours=cols,
                          bg=(236, 238, 242))
            sheet.append(png)
            print(part["name"], f"{len(part['mesh'].faces)} faces")

    # the set of four on one plate, 2 x 2: fits a 256 or 270 mm bed
    for suffix in ("", "_logo"):
        four = [parts_by[f"wd_infill_{p}{suffix}"] for p in PATTERNS]
        (out_dir / f"wd_infill_set{suffix}.3mf").write_bytes(
            designs.export(four, palette, gap=6.0, row_w=2 * D + 6.5))

    from PIL import Image
    ims = [Image.open(p) for p in sheet]
    w, h = ims[0].size
    img = Image.new("RGB", (w * 4, h * 2), (236, 238, 242))
    for i, im in enumerate(ims):
        img.paste(im, ((i % 4) * w, (i // 4) * h))
    img.save(prev_dir / "infill_set.png")


if __name__ == "__main__":
    main()
