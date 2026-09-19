"""The case as a solid, for when you would rather slice it yourself.

The g-code writer is the point of this package, but an STL is what you want
if you are going to paint the case in your slicer's own colour tool, look at
it before printing, or take the shape somewhere else. So this builds the same
case as a mesh -- from the same :class:`~phonecase.spec.CaseSpec`, not from
the toolpath, so it is the real shape rather than a trace of the beads.

It is deliberately not marching anything. A phone case is mostly flat faces
and straight walls, and putting a grid through it turns a back plate that
wants a hundred triangles into three hundred thousand. Instead every surface
here is what it actually is:

* the outer shell, the cavity and the lip are **tubes**: a stack of rounded
  rectangles with matching vertex counts, stitched into a watertight solid.
  The chamfer at the base and the taper of the lip are one ring-to-ring loft
  each, so they are exact rather than stepped.
* every cutout is a **convex prism** -- the back ones through the plate, the
  side ones through the wall, each one the same rounded rectangle in the
  same ``(u, z)`` plane the g-code writer uses.

Which leaves exactly one thing that needs a library: subtracting them.
:mod:`manifold3d` does that, and it is the only import here that is not
standard library. Everything else -- the rounded rectangles, the half-plane
clip, the lofts, the binary STL -- is written out, because it is a few dozen
lines each and a dependency you do not take is a dependency that cannot
break your build.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from .spec import CaseSpec, Cutout

Point = tuple[float, float]
Vert = tuple[float, float, float]
Tri = tuple[int, int, int]

#: What to install if it is missing. Kept as a string so the import error
#: can say it without importing anything.
REQUIRES = "manifold3d"


class MeshUnavailable(RuntimeError):
    """Raised when the one optional dependency is not installed."""


def _manifold_module():
    try:
        import manifold3d
    except ImportError:
        raise MeshUnavailable(
            "building a solid needs the manifold3d package for the boolean "
            f"("  "pip install " + REQUIRES + "). The g-code writer does not "
            "need it, which is why it is not a hard requirement") from None
    return manifold3d


# --------------------------------------------------------------------------
# 2D
# --------------------------------------------------------------------------

def _segs(r: float, tol: float) -> int:
    """Points per quarter turn so the chord never sags more than ``tol``."""
    if r <= tol:
        return 1
    return max(2, int(math.ceil((math.pi / 2) / (2 * math.acos(1 - tol / r)))))


def _rrect(hx: float, hy: float, r: float, seg: int, *,
           cx: float = 0.0, cy: float = 0.0) -> list[Point]:
    """A rounded rectangle, counter-clockwise, ``seg`` points per corner.

    ``seg`` is passed in rather than worked out here because a tube is
    stitched ring to ring by index, so every ring in one has to agree on how
    many points it has.
    """
    r = max(0.0, min(r, hx, hy))
    ax, ay = hx - r, hy - r
    if r <= 0.0 or seg <= 1:
        return [(cx + ax, cy - ay), (cx + ax, cy + ay),
                (cx - ax, cy + ay), (cx - ax, cy - ay)]
    # Each quarter is sampled from end to end *inclusive*, so the four points
    # where the arc is tangent to the sides are always hit exactly. Stopping
    # one sample short instead leaves the closing chord cutting the corner --
    # which on a stadium (r == hy, no straight top or bottom) means its flat
    # side sits a tenth of a millimetre proud of where it should be, and a
    # cutout built from it does not quite reach through.
    out: list[Point] = []
    for ox, oy, a0 in ((ax, -ay, -math.pi / 2), (ax, ay, 0.0),
                       (-ax, ay, math.pi / 2), (-ax, -ay, math.pi)):
        for i in range(seg + 1):
            a = a0 + (math.pi / 2) * i / seg
            pt = (cx + ox + r * math.cos(a), cy + oy + r * math.sin(a))
            # Neighbouring quarters share a point when the rectangle has no
            # straight side between them.
            if out and math.dist(out[-1], pt) < 1e-9:
                continue
            out.append(pt)
    if len(out) > 1 and math.dist(out[0], out[-1]) < 1e-9:
        out.pop()
    return out


def _clip_above(poly: list[Point], y_min: float) -> list[Point]:
    """Sutherland-Hodgman against ``y >= y_min``.

    Only ever used on a convex polygon, which is what keeps the fan cap in
    :func:`_tube` honest.
    """
    out: list[Point] = []
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        a_in, b_in = ay >= y_min, by >= y_min
        if a_in:
            out.append((ax, ay))
        if a_in != b_in and by != ay:
            t = (y_min - ay) / (by - ay)
            out.append((ax + (bx - ax) * t, y_min))
    return out


# --------------------------------------------------------------------------
# 3D
# --------------------------------------------------------------------------

@dataclass
class Mesh:
    """A triangle soup with shared vertices. Deliberately plain."""

    verts: list[Vert]
    tris: list[Tri]

    def transformed(self, fn) -> "Mesh":
        """Map every vertex, flipping the winding if ``fn`` mirrors space."""
        verts = [fn(v) for v in self.verts]
        e1 = _sub(fn((1, 0, 0)), fn((0, 0, 0)))
        e2 = _sub(fn((0, 1, 0)), fn((0, 0, 0)))
        e3 = _sub(fn((0, 0, 1)), fn((0, 0, 0)))
        det = (e1[0] * (e2[1] * e3[2] - e2[2] * e3[1])
               - e1[1] * (e2[0] * e3[2] - e2[2] * e3[0])
               + e1[2] * (e2[0] * e3[1] - e2[1] * e3[0]))
        tris = [(c, b, a) for a, b, c in self.tris] if det < 0 else list(self.tris)
        return Mesh(verts, tris)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _tube(rings: list[tuple[list[Point], float]]) -> Mesh:
    """Stitch a stack of rings into one closed solid.

    Every ring must have the same number of points, wound counter-clockwise,
    and they are matched by index -- which is exactly true here because the
    rings of a tube are the same rounded rectangle at different insets, built
    with the same ``seg``.

    The end caps are triangle fans from the ring's own average point. That is
    only valid for a convex ring, which every ring in this file is: a rounded
    rectangle, or a rounded rectangle cut by a half-plane.
    """
    n = len(rings[0][0])
    if any(len(pts) != n for pts, _ in rings):
        raise ValueError("every ring of a tube needs the same point count")

    verts: list[Vert] = []
    tris: list[Tri] = []
    bases: list[int] = []
    for pts, z in rings:
        bases.append(len(verts))
        verts.extend((x, y, z) for x, y in pts)

    for k in range(len(rings) - 1):
        lo, hi = bases[k], bases[k + 1]
        for i in range(n):
            j = (i + 1) % n
            tris.append((lo + i, lo + j, hi + j))
            tris.append((lo + i, hi + j, hi + i))

    for base, (pts, z), bottom in ((bases[0], rings[0], True),
                                   (bases[-1], rings[-1], False)):
        cx = sum(p[0] for p in pts) / n
        cy = sum(p[1] for p in pts) / n
        c = len(verts)
        verts.append((cx, cy, z))
        for i in range(n):
            j = (i + 1) % n
            tris.append((c, base + j, base + i) if bottom
                        else (c, base + i, base + j))
    return Mesh(verts, tris)


# --------------------------------------------------------------------------
# the case
# --------------------------------------------------------------------------

def _cutter(c: Cutout, spec: CaseSpec, seg: int) -> Mesh | None:
    """One cutout as a closed prism, in case coordinates.

    A back cutout is a prism up the z axis through the plate. A side cutout
    is the same rounded rectangle the g-code writer uses in the unrolled
    ``(u, z)`` plane, stopped flat at the back plate for the same reason --
    a hole through the plate edge leaves nothing joining the two halves of
    the wall -- and then pushed through the wall.
    """
    if c.face == "back":
        poly = _rrect(c.w / 2, c.h / 2, c.r, seg, cx=c.u, cy=c.v)
        # A shade past the cavity floor rather than exactly on it: a
        # coincident face is the classic way to confuse a boolean.
        return _tube([(poly, -1.0), (poly, spec.back_thickness + 0.02)])

    poly = _clip_above(_rrect(c.w / 2, c.h / 2, c.r, seg, cx=c.u, cy=c.v),
                       spec.back_thickness)
    if len(poly) < 3:
        return None
    deep = spec.wall + 2.0
    prism = _tube([(poly, -deep), (poly, deep)])

    # Local (p, q, s) is (along the face, up, through it). Mapping it into
    # place mirrors space for two of the four faces, and Mesh.transformed
    # flips the winding when it does.
    if c.face in ("bottom", "top"):
        y = spec.outer_l / 2 * (1 if c.face == "top" else -1)
        return prism.transformed(lambda v: (v[0], y + v[2], v[1]))
    x = spec.outer_w / 2 * (1 if c.face == "right" else -1)
    return prism.transformed(lambda v: (x + v[2], v[0], v[1]))


def build_solid(spec: CaseSpec, *, tol: float = 0.02, test_fit: bool = False):
    """The case as a :class:`manifold3d.Manifold`.

    ``tol`` is how far a flat chord may sag from the true arc, in mm. At the
    0.02 default a corner is a hundred-odd points and the whole case is a few
    thousand triangles -- smooth past what a 0.4 mm nozzle can resolve, and
    small enough to open instantly.
    """
    if test_fit:
        raise ValueError(
            "--test-fit is a toolpath trick: it leaves the middle of the back "
            "plate unfilled, which is a thing g-code can say and a solid "
            "cannot. Export the whole case, or take the test fit as g-code")

    mod = _manifold_module()
    H = spec.height
    seg = _segs(spec.outer_r, tol)

    def outer_ring(inset: float) -> list[Point]:
        return _rrect(spec.outer_w / 2 - inset, spec.outer_l / 2 - inset,
                      spec.outer_r - inset, seg)

    def inner_ring(inset: float) -> list[Point]:
        return _rrect(spec.inner_w / 2 - inset, spec.inner_l / 2 - inset,
                      max(0.05, spec.inner_r - inset), seg)

    c = spec.base_chamfer
    outer_rings = ([(outer_ring(c), 0.0), (outer_ring(0.0), c)] if c > 0
                   else [(outer_ring(0.0), 0.0)])
    outer_rings.append((outer_ring(0.0), H))

    # The cavity runs a millimetre past the top so its own end cap is never
    # coplanar with the rim the outer solid is about to cut it against.
    cavity_rings = [(inner_ring(0.0), spec.back_thickness)]
    if spec.lip > 0 and spec.lip_inset > 0:
        cavity_rings.append((inner_ring(0.0), H - spec.lip))
        cavity_rings.append((inner_ring(spec.lip_inset), H))
        cavity_rings.append((inner_ring(spec.lip_inset), H + 1.0))
    else:
        cavity_rings.append((inner_ring(0.0), H + 1.0))

    solid = _to_manifold(mod, _tube(outer_rings))
    solid = solid - _to_manifold(mod, _tube(cavity_rings))
    for cut in spec.cutouts:
        mesh = _cutter(cut, spec, _segs(max(cut.r, 0.2), tol))
        if mesh is not None:
            solid = solid - _to_manifold(mod, mesh)
    return solid


def _to_manifold(mod, mesh: Mesh):
    import numpy as np
    m = mod.Manifold(mod.Mesh(
        vert_properties=np.asarray(mesh.verts, dtype=np.float32),
        tri_verts=np.asarray(mesh.tris, dtype=np.uint32)))
    if m.status() != mod.Error.NoError:
        raise ValueError(f"built a solid the boolean will not take: {m.status()}")
    return m


# --------------------------------------------------------------------------
# STL
# --------------------------------------------------------------------------

def to_stl(spec: CaseSpec, *, tol: float = 0.02, header: str = "") -> bytes:
    """The case as a binary STL.

    Binary rather than ASCII: a fifth of the size, and nothing reads the
    facet normals anyway -- they are written as zero, which every slicer
    takes as "work it out from the winding", the same as it has to do for
    the half of the STLs in the world whose normals disagree with their
    triangles.
    """
    return mesh_to_stl(build_solid(spec, tol=tol), header=header)


def mesh_to_stl(solid, *, header: str = "") -> bytes:
    mesh = solid.to_mesh()
    verts = mesh.vert_properties[:, :3]
    tris = mesh.tri_verts
    head = header.encode()[:79].ljust(80, b"\0")
    out = bytearray(head)
    out += struct.pack("<I", len(tris))
    pack = struct.Struct("<12fH").pack
    for a, b, c in tris:
        va, vb, vc = verts[a], verts[b], verts[c]
        out += pack(0.0, 0.0, 0.0,
                    float(va[0]), float(va[1]), float(va[2]),
                    float(vb[0]), float(vb[1]), float(vb[2]),
                    float(vc[0]), float(vc[1]), float(vc[2]), 0)
    return bytes(out)


def stats(solid) -> dict:
    """Numbers worth printing next to the file size."""
    mesh = solid.to_mesh()
    v = mesh.vert_properties[:, :3]
    return {
        "triangles": int(len(mesh.tri_verts)),
        "vertices": int(len(v)),
        "volume_mm3": float(solid.volume()),
        "genus": int(solid.genus()),
        "bbox": [[float(v[:, i].min()) for i in range(3)],
                 [float(v[:, i].max()) for i in range(3)]],
    }
