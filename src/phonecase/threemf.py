"""The case as a 3MF, with the artwork carried as inlays the slicer can see.

An STL is one colour by construction. A 3MF can hold several, and the way it
holds them is what decides whether your slicer opens the file already knowing
which filament goes where: one object per colour, grouped into a single
object by ``<components>``, with a ``<basematerials>`` list they point into.
That is the structure the card generator in the sibling repository uses, and
the reason to copy it rather than invent one is that it is the structure
known to survive the trip into a real slicer.

The geometry is the interesting part. The artwork is a picture painted on a
flat face at a resolution far finer than the mesh, so carrying it means
cutting the back plate into pieces that *are* the picture:

* Each SVG shape becomes a 2-D region in case coordinates, and the stack is
  walked from the top down so a shape is kept only where nothing drawn after
  it covers it. That is the painter's rule the raster already follows, done
  once per shape rather than once per pair.
* Each colour's region is extruded to the depth of the artwork layers and
  intersected with the case, which trims it to the back plate and around the
  camera opening for nothing.
* The body is the case with those inlays taken out of it.

So the parts stack up to exactly the case: no overlaps, no gaps, and the
same shape the g-code prints. What it cannot carry is *how* the printer gets
there -- the purge tower, the tool-change ordering, the per-layer flush --
because none of that is geometry. The g-code remains the thing that prints;
this is the thing you can slice yourself.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from .paint import PaintPlan
from .solid import MeshUnavailable, _manifold_module, build_solid
from .spec import CaseSpec

#: 3MF is an OPC package -- a zip with a content-type map and a relationship
#: pointing at the model. These three strings are the whole envelope.
_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
    'package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.'
    '3dmanufacturing-3dmodel+xml"/>'
    '</Types>')

_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    '</Relationships>')


@dataclass
class Part:
    """One solid in one filament."""

    name: str
    slot: int
    rgb: tuple[int, int, int]
    solid: object                                # manifold3d.Manifold

    @property
    def hex(self) -> str:
        return "#%02X%02X%02XFF" % self.rgb


def art_top(spec: CaseSpec) -> float:
    """Height of the artwork layers: how deep an inlay has to be."""
    zs = spec.layer_zs()
    return zs[min(spec.art_layers, len(zs)) - 1][0]


def _regions(plan: PaintPlan, mod) -> dict[int, object]:
    """The visible 2-D region of each slot, in case coordinates.

    Walking the stack from the top down and keeping what has already been
    covered gives each shape's visible part in one pass. Doing it the other
    way round -- subtracting every later shape from each shape in turn -- is
    the same answer for a boolean per pair of shapes.
    """
    art = plan.art
    if art is None:
        return {}
    place = plan.placement
    covered = mod.CrossSection()
    stacks: dict[int, list] = {}
    for shape in reversed(art.shapes):
        loops = [[place.apply(p) for p in sp]
                 for sp in shape.subpaths if len(sp) >= 3]
        if not loops:
            continue
        rule = mod.FillRule.EvenOdd if shape.even_odd else mod.FillRule.NonZero
        poly = mod.CrossSection(loops, rule)
        if poly.is_empty():
            continue
        visible = poly - covered
        covered = covered + poly
        if not visible.is_empty():
            stacks.setdefault(plan.palette.match(shape.rgb), []).append(visible)

    out = {}
    for slot, pieces in stacks.items():
        region = (pieces[0] if len(pieces) == 1
                  else mod.CrossSection.batch_boolean(pieces, mod.OpType.Add))
        # Thinning the outline costs nothing anyone can see at a 0.4 mm
        # nozzle and keeps a detailed drawing from becoming a vast mesh.
        region = region.simplify(0.01)
        if not region.is_empty():
            out[slot] = region
    return out


def colour_parts(spec: CaseSpec, plan: PaintPlan, *, tol: float = 0.02,
                 wrap: bool = False) -> list[Part]:
    """The case split into one solid per filament, body first."""
    mod = _manifold_module()
    case = build_solid(spec, tol=tol)
    base = plan.palette.base

    regions = _regions(plan, mod)
    # The body is already the base colour, so a base-coloured inlay would be
    # a second part in the same filament and nothing but extra triangles.
    regions.pop(base, None)

    depth = spec.height if wrap else art_top(spec)
    parts: list[Part] = []
    inlays = []
    for slot in sorted(regions):
        solid = mod.Manifold.batch_boolean(
            [case, regions[slot].extrude(depth)], mod.OpType.Intersect)
        if solid.is_empty() or solid.volume() < 1e-3:
            continue                             # fell off the case entirely
        s = plan.palette.slots[slot]
        parts.append(Part(s.name, slot, s.rgb, solid))
        inlays.append(solid)

    body = case
    for solid in inlays:
        body = body - solid
    bs = plan.palette.slots[base]
    return [Part(bs.name, base, bs.rgb, body)] + parts


# --------------------------------------------------------------------------
# writing it out
# --------------------------------------------------------------------------

def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _mesh_xml(oid: int, solid, pindex: int, name: str) -> str:
    mesh = solid.to_mesh()
    v = mesh.vert_properties[:, :3]
    out = [f'<object id="{oid}" type="model" name="{_escape(name)}" '
           f'pid="1" pindex="{pindex}"><mesh><vertices>']
    out += [f'<vertex x="{p[0]:.4f}" y="{p[1]:.4f}" z="{p[2]:.4f}"/>' for p in v]
    out.append("</vertices><triangles>")
    out += [f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.tri_verts]
    out.append("</triangles></mesh></object>")
    return "".join(out)


def to_3mf(spec: CaseSpec, plan: PaintPlan, *, tol: float = 0.02,
           wrap: bool = False, name: str = "case") -> bytes:
    """Build the parts and package them."""
    return parts_to_3mf(colour_parts(spec, plan, tol=tol, wrap=wrap),
                        origin=(spec.outer_w / 2, spec.outer_l / 2), name=name)


def parts_to_3mf(parts: list[Part], *, origin=(0.0, 0.0),
                 name: str = "case") -> bytes:
    """Package parts as a 3MF: a material per filament, a component per part.

    The build item carries the shift into the positive octant rather than the
    vertices, so the numbers in the file stay the case's own coordinates and
    stay readable.
    """
    if not parts:
        raise ValueError("nothing to write")

    objects, ids = [], []
    oid = 2                                      # id 1 is the material list
    for i, part in enumerate(parts):
        objects.append(_mesh_xml(oid, part.solid, i,
                                 f"{name} T{part.slot} {part.name}"))
        ids.append(oid)
        oid += 1
    comps = "".join(f'<component objectid="{i}"/>' for i in ids)
    objects.append(f'<object id="{oid}" type="model" name="{_escape(name)}">'
                   f'<components>{comps}</components></object>')

    bases = "".join(
        f'<base name="{_escape(f"T{p.slot} {p.name}")}" displaycolor="{p.hex}"/>'
        for p in parts)
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        f'<resources><basematerials id="1">{bases}</basematerials>'
        f'{"".join(objects)}</resources>'
        f'<build><item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 '
        f'{origin[0]:.4f} {origin[1]:.4f} 0"/></build></model>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", model)
    return buf.getvalue()


def stats(parts: list[Part]) -> dict:
    """What went into the file, per filament."""
    return {
        "parts": len(parts),
        "triangles": sum(int(p.solid.to_mesh().tri_verts.shape[0]) for p in parts),
        "volume_mm3": sum(float(p.solid.volume()) for p in parts),
        "per_part": [{"slot": p.slot, "name": p.name, "hex": p.hex,
                      "volume_mm3": round(float(p.solid.volume()), 1),
                      "triangles": int(p.solid.to_mesh().tri_verts.shape[0])}
                     for p in parts],
    }
