"""Excavator bucket key holder, v2: stronger teeth, SWC branding and terrain.

A digging bucket hung on the wall by its back, mouth facing out, with a row of
teeth along the cutting edge to hang keys on. The bowl is a tray for loose
keys, a pen or a phone. Built in print orientation: back on the bed (z = 0),
x across, y up the wall, and the teeth grow up in +z.

Why v1's teeth snapped
----------------------
In v1 each black tooth was cut flush against the yellow bucket, so all that
held a tooth on was a ~13 x 6 mm face where the black met the yellow. That
face lay flat in a single layer: one filament change on one layer line, at
the exact point where a hanging key bends the tooth hardest.

What v2 changes
---------------
* The teeth no longer stop at the bucket. They grow out of a black
  **cutting-edge plate** that runs the full inside width of the floor. So at
  the root of a tooth, where it bends most, there is no colour seam at all.
* The plate is **lap-jointed** into the yellow floor and sits between the
  yellow side plates. Most of the seam between the two filaments is now
  upright walls, which bond within each layer, not across layers, and it is
  ~40x the area of v1's seam.
* **Thicker teeth.** The edge is 9 mm, up from 7. Each tooth has an adapter
  that straddles the lip, with a strap back along the floor and a boss
  rising 2.5 mm above the edge, so the root is ~16 x 11.5 mm against v1's
  ~13 x 6. Bending strength goes with width x thickness^2: about 4x.
* A 2 mm **pin channel** runs down the middle of each tooth from its blunt
  tip into the plate. Push in a 2 mm nail or a length of 1.75 mm filament
  with a drop of CA glue for steel or filament reinforcement. Left empty it
  still helps, because the slicer wraps it in extra walls.

Branding
--------
The SWC monogram in black on the yellow back wall, with SOUTHWEST
CONTRACTING under it. Topographic contour lines (a made-up hill) in black on
the yellow back wall and both side plates, and in yellow on the black
cutting-edge plate. All the artwork is inlaid 0.6 mm deep and flush with the
surface, so it prints as a colour change, not a relief.

Run: python3 keyholders/make_bucket.py   (numpy, trimesh, manifold3d, shapely,
mapbox_earcut, fonttools, scikit-image, matplotlib)
"""
import os, sys
import numpy as np, trimesh
from trimesh.creation import box, cylinder
from shapely.geometry import Polygon, LineString, box as sbox
from shapely.ops import unary_union
from shapely import affinity
from skimage.measure import find_contours

from common import hull, u, d, x_, side_prism, keyhole, write_3mf, report, preview

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from trace_text import trace  # noqa: E402

FONT = os.path.join(HERE, "..", "src", "fonts", "Poppins-Bold.ttf")

# --- shape -------------------------------------------------------------------
W = 150                     # width across the cutting edge
H = 80                      # height on the wall
DEPTH = 58                  # cutting edge, out from the wall
LIP = 14                    # top lip, out from the wall
HEEL_R = 26                 # radius of the rounded heel
EDGE_T = 9                  # cutting edge thickness (v1: 7)
T = 5                       # shell and side plate thickness
N_TEETH = 5
TOOTH_L, TOOTH_TILT = 38, 15    # teeth length past the edge, and upward tilt in degrees
EAR_X, EAR_H, EAR_T = 26, 16, 6 # linkage ears: spacing either side, height above, thickness
KEYHOLE_X, KEYHOLE_Y = (-52, 52), 46   # moved out from +/-35 to make room for the logo

# --- strength ----------------------------------------------------------------
PLATE_BACK = 32             # black cutting-edge plate reaches this far back from the edge
PLATE_FULL = 12             # ...full thickness for this much of it, then laps over the yellow
LAP_Y = 3                   # yellow floor left under the lap
PIN_D = 2.0                 # pin channel: a 2 mm nail, or 1.75 mm filament + CA glue

# --- artwork -----------------------------------------------------------------
INLAY = 0.6                 # how deep the colour goes (3 layers at 0.2)
LINE_W = 0.9                # contour line width, ~2 extrusions of a 0.4 nozzle
CONTOUR_STEP = 3.6          # rough spacing of the contour lines
LOGO = "SWC"
LOGO_H = 22                 # cap height of the monogram
TAGLINE = "SOUTHWEST CONTRACTING"
TAGLINE_H = 4.2
SEED = 42                   # change for a different hill

YELLOW = (0xF2, 0xB7, 0x05)
BLACK = (0x22, 0x22, 0x22)


def arc(cz, cy, r, a0, a1, n=24):
    return [(cz + r*np.cos(a), cy + r*np.sin(a)) for a in np.linspace(np.radians(a0), np.radians(a1), n)]


# ============================================================================
# Bucket body (same outline as v1, thicker edge)
# ============================================================================
c45 = HEEL_R*(1 - np.cos(np.radians(45)))
OUTER = [(0, 2*c45)] + arc(HEEL_R, HEEL_R, HEEL_R, 225, 270) + [(DEPTH, 0), (DEPTH, EDGE_T), (LIP, H), (0, H)]
shell = side_prism(OUTER, -W/2, W/2)

r_in = HEEL_R - T
slope = EDGE_T / (DEPTH - HEEL_R)
def floor_y(z): return T + slope*(z - HEEL_R)
far = DEPTH + 40
cavity = arc(HEEL_R, HEEL_R, r_in, 180, 270) + [(far, floor_y(far)), (far, H - T), (T, H - T)]
body = d(shell, side_prism(cavity, -W/2 + T, W/2 - T))

ears = []
for s in (-1, 1):
    for x in (s*EAR_X - EAR_T/2 - 4, s*EAR_X + EAR_T/2 + 4):
        ears.append(side_prism(arc(11, H, 11, -90, 90) + [(0, H - 6), (22, H - 6), (0, H)], x - EAR_T/2, x + EAR_T/2))
    pin = cylinder(radius=3.2, height=8 + 2*EAR_T, sections=32)
    pin.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, (0, 1, 0)))
    pin.apply_translation((s*EAR_X, H + 2, 11))
    ears.append(pin)
body = u([body] + ears)
body = d(body, *sum((keyhole(x, KEYHOLE_Y) for x in KEYHOLE_X), []))

# ============================================================================
# Black cutting-edge plate, lap-jointed into the floor between the side plates
# ============================================================================
XI = W/2 - T                                        # inside face of the side plates
plate_zone = u([box(bounds=((-XI, -1, DEPTH - PLATE_FULL), (XI, 40, DEPTH + 1))),
                box(bounds=((-XI, LAP_Y, DEPTH - PLATE_BACK), (XI, 40, DEPTH + 1)))])
plate = x_(body, plate_zone)
yellow = d(body, plate_zone)

# ============================================================================
# Teeth: strap along the floor + adapter over the lip + tip, all one with the plate
# ============================================================================
pitch = (W - 2*T - 16) / (N_TEETH - 1)
TEETH_X = (np.arange(N_TEETH) - (N_TEETH - 1)/2) * pitch
BOSS = EDGE_T + 2.5                                  # adapter top, 2.5 mm proud of the edge
STRAP_W = 6


def tilt(x):
    return trimesh.transformations.rotation_matrix(np.radians(-TOOTH_TILT), (1, 0, 0), (x, EDGE_T/2, DEPTH))


def tooth(x):
    # strap on the floor, rising from flush to the boss height at the lip (not tilted)
    zs = [DEPTH - PLATE_BACK + 6, DEPTH - PLATE_FULL, DEPTH]
    tops = [floor_y(zs[0]) + 0.3, floor_y(zs[1]) + 2.5, BOSS]
    strap = hull([(x + sx*STRAP_W, y, z) for sx in (-1, 1) for z, top in zip(zs, tops) for y in (LAP_Y, top)])
    # adapter: root block inside the plate out to a shoulder, then the tip
    root = [(x + sx*8, y, DEPTH - PLATE_FULL) for sx in (-1, 1) for y in (0, EDGE_T)]
    root += [(x + sx*8, y, DEPTH) for sx in (-1, 1) for y in (0, BOSS)]
    shoulder = [(x + sx*7.5, y, DEPTH + 10) for sx in (-1, 1) for y in (0.5, BOSS)]
    point = [(x + sx*4, y, DEPTH + TOOTH_L) for sx in (-1, 1) for y in (EDGE_T - 3.5, EDGE_T + 1.5)]
    adapter, tip = hull(root + shoulder), hull(shoulder + point)
    for m in (adapter, tip):
        m.apply_transform(tilt(x))
    return u([strap, adapter, tip])


def pin_channel(x):
    tip_c = trimesh.transform_points([(x, EDGE_T - 1.8, DEPTH + TOOTH_L + 1)], tilt(x))[0]
    back = np.array((x, 5.2, DEPTH - 16))
    return cylinder(radius=PIN_D/2, segment=(back, tip_c), sections=24)


teeth = u(tooth(x) for x in TEETH_X)
teeth = x_(teeth, box(bounds=((-500, 0, 0), (500, 500, 500))))   # tilting drops the root below the floor
black = u([plate, teeth])
black = d(black, *[pin_channel(x) for x in TEETH_X])
yellow = d(yellow, black)


# ============================================================================
# Artwork: 2D shapes, extruded into thin slabs at a face, kept where they hit
# ============================================================================
def as_polys(g):
    if g.is_empty:
        return []
    return [p for p in getattr(g, "geoms", [g]) if isinstance(p, Polygon) and p.area > 0.6]


def slab(polys, a0, a1, frame):
    """Extrude 2D polygons from a0 to a1 along a face normal. `frame` maps the
    2D (a, b) and the extrusion c to x, y, z: "xy" for faces facing z,
    "zy" for faces facing x, "xz" for faces facing y."""
    ms = []
    for p in polys:
        m = trimesh.creation.extrude_polygon(p, a1 - a0)
        m.apply_translation((0, 0, a0))
        a, b, c = m.vertices.T
        m.vertices = {"xy": np.c_[a, b, c], "zy": np.c_[c, b, a], "xz": np.c_[a, c, b]}[frame]
        if frame in ("zy", "xz"):          # these swaps mirror the mesh, so turn it back the right way out
            m.invert()
        ms.append(m)
    return trimesh.util.concatenate(ms) if ms else None


def terrain(bounds, seed, step=CONTOUR_STEP):
    """Contour lines of a made-up hill over `bounds`, as buffered shapely lines."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = bounds
    res = 0.4
    gx, gy = np.meshgrid(np.arange(x0 - 5, x1 + 5, res), np.arange(y0 - 5, y1 + 5, res))
    h = np.zeros_like(gx)
    span = max(x1 - x0, y1 - y0)
    n = max(6, int((x1 - x0)*(y1 - y0) / 450))      # hills and hollows, more on a bigger face
    for _ in range(n):
        cx, cy = rng.uniform(x0 - 5, x1 + 5), rng.uniform(y0 - 5, y1 + 5)
        s = rng.uniform(0.07, 0.18)*span
        h += rng.choice([-1, 1]) * rng.uniform(0.5, 1.0) * np.exp(-((gx - cx)**2 + (gy - cy)**2) / (2*s*s))
    for _ in range(3):                              # a little ripple so it reads as ground, not a lens
        k = rng.uniform(0.05, 0.14); a = rng.uniform(0, np.pi)
        h += 0.06*np.sin(k*(np.cos(a)*gx + np.sin(a)*gy) + rng.uniform(0, 6))

    # levels spaced so the lines come out ~`step` apart where the slope is average
    g = np.hypot(*np.gradient(h, res))
    dl = np.mean(g) * step
    lines = []
    for lv in np.arange(h.min() + dl/2, h.max(), dl):
        for c in find_contours(h, lv):
            if len(c) > 6:
                pts = np.c_[x0 - 5 + c[:, 1]*res, y0 - 5 + c[:, 0]*res]
                lines.append(LineString(pts).simplify(0.08))
    ink = unary_union([ln.buffer(LINE_W/2, quad_segs=4) for ln in lines])
    # where lines crowd together they fuse into a solid patch: drop those
    return unary_union([p for p in as_polys(ink) if p.buffer(-LINE_W*0.75).is_empty or p.area < 4])


def text_shapes(s, cap_h, cx, cy, tracking=0.0):
    shapes = unary_union(trace(s, FONT, tracking))
    x0, y0, x1, y1 = shapes.bounds
    k = cap_h / (y1 - y0)
    shapes = affinity.scale(shapes, k, k, origin=(0, 0))
    x0, y0, x1, y1 = shapes.bounds
    return affinity.translate(shapes, cx - (x0 + x1)/2, cy - (y0 + y1)/2)


# --- back wall, inside face (z = T): logo + terrain, black on yellow ---------
BACK = sbox(-XI + 2.5, HEEL_R + 1.5, XI - 2.5, H - T - 2.5)      # flat part of the back wall
logo = text_shapes(LOGO, LOGO_H, 0, 56, tracking=0.04)
tag = text_shapes(TAGLINE, TAGLINE_H, 0, 37.5, tracking=0.12)
underline = sbox(logo.bounds[0], 42.6, logo.bounds[2], 43.6)
brand = unary_union([logo, tag, underline])
holes = unary_union([sbox(x - 7, KEYHOLE_Y - 7, x + 7, KEYHOLE_Y + 16) for x in KEYHOLE_X])
keep_clear = unary_union([brand.buffer(6).buffer(-3.4), holes])   # closed up, so no lines in the C's mouth
back_art = unary_union([brand, terrain(BACK.bounds, SEED).intersection(BACK).difference(keep_clear)])
art_black = [slab(as_polys(back_art), T - INLAY, T + 0.05, "xy")]

# --- side plates, outer faces (x = +/-W/2): terrain, black on yellow ---------
side = Polygon(OUTER).buffer(-2.5)
for sgn, seed in ((1, SEED + 1), (-1, SEED + 2)):
    lines = terrain(side.bounds, seed).intersection(side)
    if sgn > 0:
        art_black.append(slab(as_polys(lines), W/2 - INLAY, W/2 + 0.05, "zy"))
    else:
        art_black.append(slab(as_polys(lines), -W/2 - 0.05, -W/2 + INLAY, "zy"))

# --- cutting-edge plate, top face: terrain, yellow on black ------------------
plate_top = sbox(-XI + 2, DEPTH - PLATE_BACK + 4, XI - 2, DEPTH - 3.5)    # in (x, z)
straps = unary_union([sbox(x - STRAP_W - 1.2, 0, x + STRAP_W + 1.2, 200) for x in TEETH_X])
edge_lines = terrain(plate_top.bounds, SEED + 3, step=3.0).intersection(plate_top).difference(straps)
edge_cols = slab(as_polys(edge_lines), -1, 40, "xz")
# the plate's top here is the sloping floor, y = floor_y(z): keep INLAY under it
za, zb = DEPTH - PLATE_BACK, DEPTH
skin = side_prism([(za, floor_y(za) - INLAY), (zb, floor_y(zb) - INLAY), (zb, floor_y(zb) + 0.05), (za, floor_y(za) + 0.05)], -XI, XI)
# all black under the floor here, so no clip to it; the top sits 0.05 mm proud so it is
# never coplanar with the floor (that left paper-thin flaps the slicer calls non-manifold)
art_yellow = x_(edge_cols, skin)

art_black = x_(u(m for m in art_black if m is not None), yellow)
yellow = u([d(yellow, art_black), art_yellow])
black = u([d(black, art_yellow), art_black])


def drop_slivers(m, min_vol=0.05):
    """The inlay booleans leave a few zero-volume sliver shells; slicers trip on them."""
    shells = [s for s in m.split(only_watertight=False) if abs(s.volume) >= min_vol]
    return trimesh.util.concatenate(shells)


yellow, black = drop_slivers(yellow), drop_slivers(black)

parts = [("bucket (yellow)", YELLOW, yellow), ("teeth, edge and art (black)", BLACK, black)]
if __name__ == "__main__":
    write_3mf(parts, HERE + "/bucket.3mf", "excavator bucket key holder SWC")
    report(parts)
    preview(parts, HERE + "/bucket.png", azim=-55, elev=25)
    preview(parts, HERE + "/bucket_front.png", azim=-88, elev=8)
    preview(parts, HERE + "/bucket_side.png", azim=-5, elev=10)
