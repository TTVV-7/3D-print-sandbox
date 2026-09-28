"""The phone, and the case on it, as one GLB for the page's 3D view.

    glb = phone_mockup.glb(spec, paint, finish="silver")

The phone is built from the same numbers the case is -- src/phonecase/spec.py
-- rather than downloaded from somewhere, for three reasons.  It fits: the body
is the published size and corner radius, the camera bump is the camera opening
less the clearance, the lenses are where the flat preview draws them and the
buttons are where the case cuts for them, so the phone sits in the case the
way the case was designed round it.  Every phone in the table gets one, drawn
the same way, and a new phone added to the table gets one too.  And it is a
generic slab with the right proportions, not a copy of anybody's industrial
design: no logo, no trade dress.

It is an illustration, and it is only as right as those numbers.  Where the
table's camera opening is wrong, the phone drawn here is wrong in exactly the
same way and the two will look like a perfect fit regardless -- which is why
the test fit on a real phone is still the thing that counts.

The case is the real one: phonecase.threemf.colour_parts, the same solids the
3MF download is made of, body and artwork inlays each in its own colour.

Kept out of src/phonecase/ because that package is vendored from
ttvv-7/weave-trial and PROVENANCE records which commit it is a copy of.
"""
from __future__ import annotations

import io
import math

import numpy as np
import trimesh

from phonecase.preview import _lens_layout
from phonecase.solid import _rrect, _segs, _tube
from phonecase.threemf import colour_parts

# How the phone is finished, per phone, as (name, frame colour).  The first
# is the default.  A phone not listed gets the generic pair.
FINISHES = {
    "iphone-17-pro": [("Silver", "#d6d6d2"), ("Cosmic Orange", "#d9692e"),
                      ("Deep Blue", "#2f3e5a")],
    "iphone-17-pro-max": [("Silver", "#d6d6d2"), ("Cosmic Orange", "#d9692e"),
                          ("Deep Blue", "#2f3e5a")],
}
GENERIC = [("Silver", "#d6d6d2"), ("Graphite", "#4a4c50")]

# Estimates, like the camera numbers they sit on: how far the camera bump
# stands off the back, and the lens rings off the bump.
BUMP = 1.2
LENS = 1.3
EDGE = 1.2          # radius the body's edges are rounded to
BUTTON = 0.5        # how proud a side button stands

GLASS = "#0b0c10"
LENS_GLASS = "#10131c"
PORT = "#15161a"


def finishes(phone_id):
    return FINISHES.get(phone_id, GENERIC)


def _rgba(hexc, alpha=255):
    h = hexc.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [alpha]


def _material(hexc, metal=0.0, rough=0.5, name="m"):
    return trimesh.visual.material.PBRMaterial(
        name=name, baseColorFactor=_rgba(hexc), metallicFactor=metal,
        roughnessFactor=rough)


def _mesh(m, hexc, metal=0.0, rough=0.5, name="m"):
    tm = trimesh.Trimesh(np.asarray(m.verts, float), np.asarray(m.tris), process=True)
    tm.visual = trimesh.visual.TextureVisuals(material=_material(hexc, metal, rough, name))
    return tm


def _slab(hx, hy, r, z0, z1, cx=0.0, cy=0.0, edge=0.0, tol=0.05, steps=6):
    """A rounded rectangle from z0 to z1, its top and bottom edges rounded
    over by `edge`: a stack of rings, each the outline inset along a quarter
    circle, stitched into one closed solid."""
    seg = _segs(max(r, 0.2), tol)
    edge = max(0.0, min(edge, (z1 - z0) / 2 - 1e-3, r - 0.05, hx, hy))

    def ring(inset, z):
        return (_rrect(hx - inset, hy - inset, max(0.05, r - inset), seg, cx=cx, cy=cy), z)

    if edge <= 0:
        return _tube([ring(0, z0), ring(0, z1)])
    rings = []
    for i in range(steps + 1):                       # bottom edge, outward
        a = (math.pi / 2) * i / steps
        rings.append(ring(edge - edge * math.sin(a), z0 + edge - edge * math.cos(a)))
    for i in range(steps + 1):                       # top edge, inward
        a = (math.pi / 2) * i / steps
        rings.append(ring(edge - edge * math.cos(a), z1 - edge + edge * math.sin(a)))
    return _tube(rings)


def _disc(cx, cy, r, z0, z1):
    return _slab(r, r, r, z0, z1, cx=cx, cy=cy, tol=0.01)


def phone_meshes(spec, finish_hex):
    """The phone, as (name, trimesh) pairs, in case coordinates: its back on
    the case's back plate, its camera bump down through the opening."""
    p = spec.phone
    z0 = spec.back_thickness
    z1 = z0 + p.thickness
    hx, hy = p.width / 2, p.length / 2
    out = []

    body = _slab(hx, hy, p.corner_radius, z0, z1, edge=EDGE)
    out.append(("phone-body", _mesh(body, finish_hex, metal=0.85, rough=0.32, name="frame")))

    # The front: one sheet of black glass over the flat of the top, and the
    # camera cut-out at the top of the display as a slightly deeper black.
    inset = EDGE + 0.15
    out.append(("phone-screen", _mesh(
        _slab(hx - inset, hy - inset, p.corner_radius - inset, z1 - 0.02, z1 + 0.06),
        GLASS, metal=0.1, rough=0.06, name="screen")))
    island_w, island_h = min(20.0, p.width * 0.28), 5.6
    out.append(("phone-island", _mesh(
        _slab(island_w / 2, island_h / 2, island_h / 2, z1 + 0.06, z1 + 0.07,
              cy=hy - inset - 4.0 - island_h / 2),
        "#000000", metal=0.0, rough=0.2, name="island")))

    # The camera: the bump is the opening less the clearance all round, so it
    # drops into the hole with the fit gap the case was drawn with; the lenses
    # are where the flat preview puts them.
    cam = next(c for c in spec.cutouts if c.name == "camera")
    g = spec.clearance + 0.25
    bump = _slab(cam.w / 2 - g, cam.h / 2 - g, max(0.3, cam.r - g), z0 - BUMP, z0 + 0.1,
                 cx=cam.u, cy=cam.v, edge=0.4)
    out.append(("phone-camera", _mesh(bump, finish_hex, metal=0.85, rough=0.3, name="bump")))
    zb = z0 - BUMP
    for i, (dx, dy, r, is_lens) in enumerate(_lens_layout(p, cam)):
        x, y = cam.u + dx, cam.v + dy
        if is_lens:
            out.append((f"phone-lens-ring-{i}", _mesh(
                _slab(r, r, r, zb - LENS, zb + 0.05, cx=x, cy=y, edge=0.35, tol=0.01),
                "#2a2b30", metal=0.9, rough=0.25, name="lens-ring")))
            out.append((f"phone-lens-{i}", _mesh(
                _disc(x, y, r * 0.66, zb - LENS - 0.04, zb - LENS + 0.1),
                LENS_GLASS, metal=0.2, rough=0.04, name="lens")))
        else:
            # On a bar, the flash and the depth sensor sit one above the
            # other at the far end from the lenses.
            stacked = p.camera_style == "plateau" and p.lenses >= 3
            fy = y + r * 1.3 if stacked else y
            out.append((f"phone-flash-{i}", _mesh(
                _disc(x, fy, r, zb - 0.05, zb + 0.05), "#e8e4d8", rough=0.3, name="flash")))
            if stacked:
                out.append((f"phone-sensor-{i}", _mesh(
                    _disc(x, y - r * 1.3, r * 0.85, zb - 0.05, zb + 0.05),
                    "#050507", rough=0.15, name="sensor")))

    # Side buttons, where the case cuts for them.
    zm = (z0 + z1) / 2
    for name, face, offset, length in p.buttons:
        if face in ("left", "right"):
            x = (hx + BUTTON / 2 - 0.3) * (1 if face == "right" else -1)
            m = _slab(BUTTON / 2 + 0.3, length / 2, min(1.0, length / 2), zm - 1.2, zm + 1.2,
                      cx=x, cy=offset)
        else:
            y = (hy + BUTTON / 2 - 0.3) * (1 if face == "top" else -1)
            m = _slab(length / 2, BUTTON / 2 + 0.3, min(1.0, length / 2), zm - 1.2, zm + 1.2,
                      cx=offset, cy=y)
        out.append((f"phone-button-{name}", _mesh(m, finish_hex, metal=0.85, rough=0.35,
                                                  name="button")))

    # The charging port, as a dark slot on the bottom edge.
    out.append(("phone-port", _mesh(
        _slab(4.4, 0.4, 0.39, zm - 1.3, zm + 1.3, cy=-hy + 0.25),
        PORT, rough=0.6, name="port")))
    return out


def case_meshes(spec, paint):
    """The case, as (name, trimesh) pairs: the body and one part per
    artwork colour, the same solids as the 3MF download."""
    out = []
    for part in colour_parts(spec, paint):
        m = part.solid.to_mesh()
        tm = trimesh.Trimesh(np.asarray(m.vert_properties[:, :3], float),
                             np.asarray(m.tri_verts), process=True)
        hexc = "#%02x%02x%02x" % tuple(part.rgb)
        tm.visual = trimesh.visual.TextureVisuals(
            material=_material(hexc, metal=0.0, rough=0.55, name=f"case-{part.slot}"))
        out.append((f"case-{part.slot}-{part.name}", tm))
    return out


def glb(spec, paint, finish_hex=None, phone=True):
    """The scene as GLB bytes: every mesh a named node, `phone-...` and
    `case-...`, so the page can move the case off the phone or hide either."""
    finish_hex = finish_hex or GENERIC[0][1]
    scene = trimesh.Scene()
    for name, mesh in (phone_meshes(spec, finish_hex) if phone else []) + case_meshes(spec, paint):
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    buf = io.BytesIO()
    buf.write(scene.export(file_type="glb"))
    return buf.getvalue()
