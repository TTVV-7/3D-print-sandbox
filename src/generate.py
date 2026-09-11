"""Generate car-brand Schrader valve caps as printable STLs.

Emblems come from src/logos.py (honda, bmw, mercedes, toyota).  Three cap
shapes are available for each:

  flat_top   - 14 mm knurled cap, flat top, emblem raised 0.6 mm so a single
               filament change prints the logo in a second colour.
  engraved   - same cap, emblem recessed 0.5 mm instead (paint-fill / subtle).
  badge      - knurled body flaring into an emblem-shaped plate with the logo
               raised on it, i.e. an actual badge on top of the cap.  Only
               makes sense for a logo with a distinctive silhouette (Honda);
               for the round marks the flat top is the same thing but tidier.

Edit BUILDS at the bottom to pick which brand/variant combinations to emit.

Everything is driven by the constants below; re-run the script after changing
them.  Threads are the real Schrader valve stem thread (0.305"-32 UNS, the
thread on a TR413 and friends), cut with a uniform radial clearance.

    python3 src/generate.py
"""
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon

import logos

ROOT = Path(__file__).resolve().parent.parent
STL_DIR = ROOT / "stl"

# ---------------------------------------------------------------------------
# Schrader valve stem thread: 0.305"-32 UNS  (TR413 / TR414 / most car stems)
# ---------------------------------------------------------------------------
THREAD_MAJOR_D = 7.747      # 0.305 in
THREAD_PITCH = 25.4 / 32.0  # 32 TPI -> 0.79375 mm
THREAD_CLEARANCE = 0.15     # radial gap cut into the cap; raise if it binds
THREAD_LEADIN = 0.9         # 45 deg chamfer at the mouth of the bore

# ---------------------------------------------------------------------------
# Cap bodies
# ---------------------------------------------------------------------------
FLUTE_COUNT = 18            # knurling: straight flutes, no seams, prints clean
FLUTE_DEPTH = 0.45

FLAT = dict(
    od=14.0, height=12.5, bore_depth=9.3,
    chamfer_bottom=0.8, chamfer_top=0.35,
    flute_band=(1.0, 11.4),
    emblem_rise=0.6, emblem_sink=0.5,
)

# Emblem width per brand, in mm.  The limit is the flat top face: od/2 minus
# the top chamfer = 6.65 mm of radius.  Honda's mark is a wide rounded
# rectangle whose corners eat that radius, so it has to run narrower than the
# round marks.  build_flat() checks the fit and refuses to emit a cap whose
# emblem would spill over the chamfer.
EMBLEM_W = {
    "honda": 11.9, "bmw": 13.1, "mercedes": 13.1, "toyota": 13.1,
    "audi": 13.1, "volkswagen": 13.1, "jeep": 13.1, "chevrolet": 12.8,
    "mitsubishi": 9.9, "volvo": 9.2,
}
# Mitsubishi and Volvo look narrow in that table but are not: their extreme
# points are not horizontally opposed, so they still reach the full 6.55 mm
# radius.  logos.fit_width(name, 6.55) computes these.

BADGE = dict(
    od=11.6, body_height=8.6, bore_depth=8.2,
    chamfer_bottom=0.8,
    flute_band=(1.0, 8.0),
    flare_rise=2.7, plate_thick=1.2,
    emblem_w=15.0, emblem_rise=0.7,
)

BUILDS = [
    ("honda", "flat_top"),
    ("honda", "flat_top_engraved"),
    ("honda", "badge"),
    ("bmw", "flat_top"),
    ("mercedes", "flat_top"),
    ("toyota", "flat_top"),
    ("audi", "flat_top"),
    ("volkswagen", "flat_top"),
    ("mitsubishi", "flat_top"),
    ("jeep", "flat_top"),
    ("chevrolet", "flat_top"),
    ("volvo", "flat_top"),
]

# Mesh resolution
N_THETA_BODY = 288
N_THETA_THREAD = 180
THREAD_Z_STEP = THREAD_PITCH / 16.0


# ---------------------------------------------------------------------------
# mesh helpers
# ---------------------------------------------------------------------------
def revolve(radius_fn, z_values, n_theta):
    """Watertight solid from a radius field r(z, theta), flat-capped at both ends.

    radius_fn(z, theta_array) -> radius_array.  Must stay strictly positive.
    """
    thetas = np.linspace(0.0, 2.0 * np.pi, n_theta, endpoint=False)
    z_values = np.asarray(z_values, dtype=float)
    nz = len(z_values)

    verts = np.empty((nz * n_theta + 2, 3))
    for j, z in enumerate(z_values):
        r = np.asarray(radius_fn(z, thetas), dtype=float)
        s = slice(j * n_theta, (j + 1) * n_theta)
        verts[s, 0] = r * np.cos(thetas)
        verts[s, 1] = r * np.sin(thetas)
        verts[s, 2] = z
    bot, top = nz * n_theta, nz * n_theta + 1
    verts[bot] = (0.0, 0.0, z_values[0])
    verts[top] = (0.0, 0.0, z_values[-1])

    i = np.arange(n_theta)
    i_next = (i + 1) % n_theta
    faces = []
    for j in range(nz - 1):
        a = j * n_theta + i
        b = j * n_theta + i_next
        c = (j + 1) * n_theta + i_next
        d = (j + 1) * n_theta + i
        faces.append(np.column_stack([a, b, c]))
        faces.append(np.column_stack([a, c, d]))
    faces.append(np.column_stack([np.full(n_theta, bot), i_next, i]))
    last = (nz - 1) * n_theta
    faces.append(np.column_stack([np.full(n_theta, top), last + i, last + i_next]))

    mesh = trimesh.Trimesh(verts, np.vstack(faces), process=False)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def loft(poly, z0, z1, scale0, scale1, n=None):
    """Watertight solid lofted between two uniformly scaled copies of `poly`.

    Uniform scaling keeps the vertex correspondence trivial.
    """
    ring = np.array(poly.exterior.coords)[:-1]
    if n is None:
        n = len(ring)
    lo = ring * scale0
    hi = ring * scale1
    verts = np.vstack([
        np.column_stack([lo, np.full(n, z0)]),
        np.column_stack([hi, np.full(n, z1)]),
        [[0.0, 0.0, z0], [0.0, 0.0, z1]],
    ])
    bot, top = 2 * n, 2 * n + 1
    i = np.arange(n)
    j = (i + 1) % n
    faces = np.vstack([
        np.column_stack([i, j, n + j]),
        np.column_stack([i, n + j, n + i]),
        np.column_stack([np.full(n, bot), j, i]),
        np.column_stack([np.full(n, top), n + i, n + j]),
    ])
    mesh = trimesh.Trimesh(verts, faces, process=False)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def boolean(op, meshes):
    return getattr(trimesh.boolean, op)(meshes, engine="manifold")


# ---------------------------------------------------------------------------
# thread
# ---------------------------------------------------------------------------
def thread_cutter(z0, z1, clearance=THREAD_CLEARANCE):
    """Solid male 0.305-32 thread form, grown radially by `clearance`.

    Subtracting this from a cap body leaves the matching internal thread.  The
    UN profile over one pitch, measured from the middle of a crest flat:
    crest p/8, flank 5p/16, root p/4, flank 5p/16.
    """
    p = THREAD_PITCH
    h = np.sqrt(3.0) / 2.0 * p                 # fundamental triangle height
    r_major = THREAD_MAJOR_D / 2.0 + clearance
    r_root = r_major - 5.0 / 8.0 * h           # external thread root

    # piecewise-linear profile over one pitch
    t_knots = np.array([0.0, 1, 6, 10, 15, 16]) * (p / 16.0)
    r_knots = np.array([r_major, r_major, r_root, r_root, r_major, r_major])

    def radius_fn(z, thetas):
        t = np.mod(z - p * thetas / (2.0 * np.pi), p)
        return np.interp(t, t_knots, r_knots)

    n_z = int(np.ceil((z1 - z0) / THREAD_Z_STEP)) + 1
    return revolve(radius_fn, np.linspace(z0, z1, n_z), N_THETA_THREAD)


def lead_in_cone(z_mouth, height, r_thread):
    """45 deg chamfer cut at the open end so the cap starts on the stem easily."""
    n = 128
    return revolve(
        lambda z, th: np.full_like(th, r_thread + max(0.0, (z_mouth + height) - z)),
        np.linspace(z_mouth - 0.5, z_mouth + height, 12),
        n,
    )


# ---------------------------------------------------------------------------
# emblem
# ---------------------------------------------------------------------------
def emblem_prisms(strokes, z_base, thickness):
    """One solid per stroke; the caller hands them all to a single boolean."""
    out = []
    for i, stroke in enumerate(strokes):
        mesh = trimesh.creation.extrude_polygon(stroke, thickness)
        if not mesh.is_watertight:
            raise ValueError(f"stroke {i} did not extrude to a closed solid")
        mesh.apply_translation((0.0, 0.0, z_base))
        out.append(mesh)
    return out


# ---------------------------------------------------------------------------
# bodies
# ---------------------------------------------------------------------------
def fluted_body(od, height, chamfer_bottom, chamfer_top, flute_band):
    r_out = od / 2.0
    z_lo, z_hi = flute_band
    ramp = 0.45

    def radius_fn(z, thetas):
        r = r_out
        if z < chamfer_bottom:
            r -= chamfer_bottom - z
        if chamfer_top and z > height - chamfer_top:
            r -= z - (height - chamfer_top)
        w = np.clip(min((z - z_lo) / ramp, (z_hi - z) / ramp), 0.0, 1.0)
        return r - FLUTE_DEPTH * w * (0.5 + 0.5 * np.cos(FLUTE_COUNT * thetas))

    knots = [0.0, chamfer_bottom, z_lo - ramp, z_lo, z_hi, z_hi + ramp, height]
    if chamfer_top:
        knots.append(height - chamfer_top)
    knots = sorted(k for k in set(knots) if 0.0 <= k <= height)
    z_values = []
    for a, b in zip(knots[:-1], knots[1:]):
        z_values.extend(np.linspace(a, b, max(2, int(np.ceil((b - a) / 0.25)) + 1))[:-1])
    z_values.append(height)
    return revolve(radius_fn, z_values, N_THETA_BODY)


def bored(body, bore_depth, r_thread_major):
    cutter = thread_cutter(-1.0, bore_depth)
    cone = lead_in_cone(-0.5, THREAD_LEADIN + 0.5, r_thread_major)
    return boolean("difference", [body, cutter, cone])


# ---------------------------------------------------------------------------
# variants
# ---------------------------------------------------------------------------
def build_flat(brand, engraved=False):
    c = FLAT
    r_thread = THREAD_MAJOR_D / 2.0 + THREAD_CLEARANCE

    strokes = logos.load(brand, EMBLEM_W[brand])
    limit = c["od"] / 2.0 - c["chamfer_top"]
    if logos.max_radius(strokes) > limit:
        raise ValueError(f"{brand}: emblem reaches r={logos.max_radius(strokes):.2f} mm, "
                         f"past the {limit:.2f} mm flat top -- shrink EMBLEM_W")

    body = fluted_body(c["od"], c["height"], c["chamfer_bottom"],
                       c["chamfer_top"], c["flute_band"])
    body = bored(body, c["bore_depth"], r_thread)

    if engraved:
        sink = c["emblem_sink"]
        cuts = emblem_prisms(strokes, c["height"] - sink, sink + 0.5)
        return boolean("difference", [body, *cuts])
    rise = c["emblem_rise"]
    add = emblem_prisms(strokes, c["height"] - 0.3, rise + 0.3)
    return boolean("union", [body, *add])


def build_badge(brand):
    c = BADGE
    r_thread = THREAD_MAJOR_D / 2.0 + THREAD_CLEARANCE
    body = fluted_body(c["od"], c["body_height"], c["chamfer_bottom"], 0.0,
                       c["flute_band"])

    strokes = logos.load(brand, c["emblem_w"])
    islands = logos.parts(logos.merged(strokes))
    if len(islands) > 1:
        raise ValueError(f"{brand}: badge plate needs a single-island emblem")
    outer = Polygon(islands[0].exterior)
    max_r = np.hypot(*np.array(outer.exterior.coords).T).max()
    scale0 = (c["od"] / 2.0) / max_r          # flare starts inside the body wall

    z_flare = c["body_height"]
    z_plate = z_flare + c["flare_rise"]
    z_top = z_plate + c["plate_thick"]

    flare = loft(outer, z_flare - 0.3, z_plate, scale0, 1.0)
    plate = emblem_prisms([outer], z_plate - 0.01, c["plate_thick"] + 0.01)
    logo = emblem_prisms(strokes, z_top - 0.3, c["emblem_rise"] + 0.3)

    solid = boolean("union", [body, flare, *plate, *logo])
    cutter = thread_cutter(-1.0, c["bore_depth"])
    cone = lead_in_cone(-0.5, THREAD_LEADIN + 0.5, r_thread)
    return boolean("difference", [solid, cutter, cone])


def report(name, mesh):
    ok = mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0
    print(f"  {name:34s} {len(mesh.faces):7d} faces  "
          f"{mesh.extents[0]:5.2f} x {mesh.extents[1]:5.2f} x {mesh.extents[2]:5.2f} mm  "
          f"{mesh.volume/1000:5.2f} cm^3  {'watertight' if ok else 'NOT WATERTIGHT'}")


def build(brand, variant):
    if variant == "flat_top":
        return build_flat(brand)
    if variant == "flat_top_engraved":
        return build_flat(brand, engraved=True)
    if variant == "badge":
        return build_badge(brand)
    raise ValueError(f"unknown variant {variant!r}")


def main():
    STL_DIR.mkdir(exist_ok=True)
    print("building:")
    for brand, variant in BUILDS:
        name = f"{brand}_valve_cap_{variant}"
        mesh = build(brand, variant)
        mesh.export(STL_DIR / f"{name}.stl")
        report(name, mesh)


if __name__ == "__main__":
    main()
