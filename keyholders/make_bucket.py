"""Excavator bucket key holder, v2: stronger teeth, SWC branding as a drawing.

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

Branding: an engineering drawing on the part itself
---------------------------------------------------
* Back wall: the SWC monogram and SOUTHWEST CONTRACTING, the inside width
  (140), the keyhole spacing (104) with centre marks, and a 9 mm diameter callout.
* Side plates: the side elevation dimensioned on the part: height 80, depth 58,
  the R26 heel with its centre lines, and the 58 degree mouth angle.
* Top: a ruler across the full 150 mm width.
* Side plates' front edges: tick marks every 5 mm up the mouth line.
* Cutting-edge plate, in yellow on black: the 31 mm tooth pitch, and notes
  (2 mm pin, 9 mm thick, 15 degree tilt, 5 places).
* Underneath: a title block.

Every number is a real dimension of this part. The artwork is inlaid flush:
0.6 mm deep on faces that lie flat or slope up in the print, and 0.8 mm on
faces that stand upright, so each layer's sliver of colour is printable.

Run: python3 keyholders/make_bucket.py   (numpy, trimesh, manifold3d, shapely,
mapbox_earcut, fonttools, pillow)
"""
import os, sys
import numpy as np, trimesh
from trimesh.creation import box, cylinder
from shapely.geometry import Polygon, LineString, box as sbox
from shapely.ops import unary_union
from shapely import affinity

from common import hull, u, d, x_, side_prism, keyhole, write_3mf, report, preview

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import drafting as df  # noqa: E402


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
LOGO = "SWC"
LOGO_H = 22                 # cap height of the monogram
TAGLINE = "SOUTHWEST CONTRACTING"
TAGLINE_H = 4.2

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
    return [p for p in getattr(g, "geoms", [g]) if isinstance(p, Polygon) and p.area > 0.2]


def slab(geom, c0, c1, origin, A, B, C):
    """Extrude 2D view geometry into a thin solid on a face.

    A point (a, b) of the view, raised c along the face's outward normal, goes
    to origin + a*A + b*B + c*C. A and B are the view's right and up as seen
    looking at the face, so text reads the right way round; c runs from c0
    (negative: into the part) to c1."""
    ms = []
    M = np.array([A, B, C], float).T
    for p in as_polys(geom):
        m = trimesh.creation.extrude_polygon(p, c1 - c0)
        m.vertices = (m.vertices + (0, 0, c0)) @ M.T + origin
        if np.linalg.det(M) < 0:            # a mirroring map turns the mesh inside out
            m.invert()
        ms.append(m)
    return trimesh.util.concatenate(ms) if ms else None


X, Y, Z = np.eye(3)
INLAY_V = 0.8      # faces that stand upright in the print get a bit more, so each layer's sliver of colour is printable
art_black = []

# --- back wall, inside face (z = T): logo, keyholes, overall width -----------
# view: x right, y up, as you face the bucket on the wall
logo = df.text(LOGO, LOGO_H, (0, 56), tracking=0.04)
tag = df.text(TAGLINE, TAGLINE_H, (0, 37.5), tracking=0.12)
underline = sbox(logo.bounds[0], 42.6, logo.bounds[2], 43.6)
back = [logo, tag, underline,
        df.dim((-52, 40.8), (52, 40.8), -10, f"{KEYHOLE_X[1] - KEYHOLE_X[0]:.0f}"),    # keyhole spacing
        df.dim((-XI + 0.6, 74.4), (XI - 0.6, 74.4), -2.8, f"{2*XI:.0f}", ext=False),  # inside width
        df.leader((55.6, 49.6), (58.3, 53.4), "Ø9", h=3.0)]
for x in KEYHOLE_X:                                          # centre marks, clear of the slot above
    c = np.array((x, KEYHOLE_Y))
    back += [df.line(c + (5.5, 0), c + (8.3, 0)), df.line(c - (5.5, 0), c - (8.3, 0)), df.line(c - (0, 5.5), c - (0, 8.3))]
back = unary_union(back).intersection(sbox(-XI + 0.3, HEEL_R + 1.3, XI - 0.3, H - T - 0.4))
art_black.append(slab(back, -INLAY, 0.05, (0, 0, T), X, Y, Z))

# --- side plates (x = +/-W/2): the side elevation, dimensioned ----------------
# view: looking at the side, y up; from the -x side z runs right, from +x it runs left


def side_view(s):
    """The side drawing in view coordinates; s = +1 for the -x side, -1 for +x."""
    V = lambda z, y: (s*z, y)
    va = lambda deg: np.degrees(np.arctan2(np.sin(np.radians(deg)), s*np.cos(np.radians(deg))))
    vertex = (DEPTH, EDGE_T)                                 # where the mouth line meets the edge
    mouth = np.degrees(np.arctan2(H - EDGE_T, LIP - DEPTH))  # direction up the mouth line
    a0, a1 = mouth + 2.5, 178
    if s < 0:
        a0, a1 = 180 - a1, 180 - a0
    g = [df.dim(V(1.2, 2*c45 + 2), V(1.2, H - 1.2), -s*4, f"{H:.0f}"),         # height
         df.dim(V(22, 1.3), V(DEPTH - 1.2, 1.3), s*4, f"{DEPTH:.0f}"),         # depth to the cutting edge
         df.radius(V(HEEL_R, HEEL_R), HEEL_R, va(225), f"R{HEEL_R:.0f}"),       # heel
         df.chain(V(10, HEEL_R), V(44, HEEL_R)), df.chain(V(HEEL_R, 9), V(HEEL_R, 44)),
         df.angle(V(*vertex), 16, a0, a1, f"{180 - mouth:.0f}°"),               # mouth line to the floor
         df.line(V(40, EDGE_T), V(DEPTH - 1.2, EDGE_T), df.LW*0.85)]
    face = affinity.scale(Polygon(OUTER), s, 1, origin=(0, 0)).buffer(-0.9)
    return unary_union(g).intersection(face)


art_black.append(slab(side_view(1), -INLAY_V, 0.05, (-W/2, 0, 0), Z, Y, -X))
art_black.append(slab(side_view(-1), -INLAY_V, 0.05, (W/2, 0, 0), -Z, Y, X))

# --- top of the bucket (y = H): a ruler across the full width -----------------
# view: looking down from in front, x right and the wall at the top (b = -z)
ears_clear = unary_union([sbox(sg*15, -30, sg*37, 5) for sg in (-1, 1)])
face_top = sbox(-W/2 + 0.7, -LIP + 0.7, W/2 - 0.7, -0.7).difference(ears_clear)
ruler = [df.line((-W/2 + 0.7, -LIP + 1.1), (W/2 - 0.7, -LIP + 1.1))]
for k in range(1, int(W // 5)):
    x = -W/2 + 5*k
    ruler.append(df.line((x, -LIP + 1.1), (x, -LIP + (6.0 if k % 2 == 0 else 3.6))))
    if k % 2 == 0:
        num = df.text(f"{5*k}", 3.0, (x, -4.2))
        if face_top.contains(num.buffer(0.4)):
            ruler.append(num)
art_black.append(slab(unary_union(ruler).intersection(face_top), -INLAY_V, 0.05, (0, H, 0), X, -Z, Y))

# --- the side plates' front edges, along the mouth: tick marks every 5 mm -----
mlen = np.hypot(H - EDGE_T, DEPTH - LIP)
mu = np.array((0, H - EDGE_T, LIP - DEPTH)) / mlen          # up the mouth line
mn = np.array((0, DEPTH - LIP, H - EDGE_T)) / mlen          # its outward normal
for sg in (-1, 1):
    ticks = [df.line((5*k, sg*(W/2 - 0.6)), (5*k, sg*(W/2 - (3.6 if k % 2 == 0 else 2.2)))) for k in range(1, int(mlen // 5))]
    art_black.append(slab(unary_union(ticks), -INLAY, 0.05, (0, EDGE_T, DEPTH), mu, X, mn))

# --- underneath (y = 0): a title block ----------------------------------------
# view: looking up at the underside, x right and the cutting edge at the top (b = z)
z0, z1 = HEEL_R + 1.2, DEPTH - PLATE_FULL - 0.8             # flat, and yellow (the black plate starts at z1)
xa, xb, zm = -42, 36, (z0 + z1)/2
tb = [df.frame(-W/2 + 1.2, z0 + 0.4, W/2 - 1.2, z1 - 0.4),
      df.line((xa, z0 + 0.4), (xa, z1 - 0.4)), df.line((xb, z0 + 0.4), (xb, z1 - 0.4)),
      df.line((xa, zm), (W/2 - 1.2, zm)),
      df.text("SWC", 7.0, ((-W/2 + xa)/2, zm), max_w=26),
      df.text("EXCAVATOR BUCKET KEY HOLDER", 3.0, ((xa + xb)/2, (zm + z1)/2), max_w=xb - xa - 4),
      df.text(TAGLINE, 3.0, ((xa + xb)/2, (z0 + zm)/2), max_w=xb - xa - 4),
      df.text("SCALE 1:1", 3.0, ((xb + W/2)/2, (zm + z1)/2), max_w=W/2 - xb - 5),
      df.text("DWG KH-02 REV B", 2.8, ((xb + W/2)/2, (z0 + zm)/2), max_w=W/2 - xb - 5)]
art_black.append(slab(unary_union(tb).intersection(sbox(-W/2 + 0.5, z0, W/2 - 0.5, z1)), -INLAY_V, 0.05, (0, 0, 0), X, Z, -Y))

# --- cutting-edge plate, top: tooth pitch and notes, yellow on black ----------
# view: looking down into the bucket, x right and the wall at the top (b = -z)
gaps = [(TEETH_X[i] + STRAP_W + 1.2, TEETH_X[i + 1] - STRAP_W - 1.2) for i in range(N_TEETH - 1)]
notes = ["Ø2 PIN", f"{EDGE_T:.0f} THK", f"{TOOTH_TILT:.0f}° TILT", f"{N_TEETH} PLCS"]
edge_art = []
for (ga, gb), note in zip(gaps, notes):
    edge_art.append(df.dim((ga + 0.4, -48), (gb - 0.4, -48), 0, f"{pitch:.0f}", h=3.0, ext=False))
    edge_art.append(df.text(note, 2.8, ((ga + gb)/2, -37.5), max_w=gb - ga - 1.5))
plate_face = sbox(-XI + 2, -(DEPTH - 3.5), XI - 2, -(DEPTH - PLATE_BACK + 4))
edge_cols = slab(unary_union(edge_art).intersection(plate_face), -1, 40, (0, 0, 0), X, -Z, Y)
# the plate's top here is the sloping floor, y = floor_y(z): keep INLAY under it
za, zb = DEPTH - PLATE_BACK, DEPTH
skin = side_prism([(za, floor_y(za) - INLAY_V), (zb, floor_y(zb) - INLAY_V), (zb, floor_y(zb) + 0.05), (za, floor_y(za) + 0.05)], -XI, XI)
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
    preview(parts, HERE + "/bucket_top.png", azim=-90, elev=80)
    preview(parts, HERE + "/bucket_under.png", azim=-90, elev=-80)
