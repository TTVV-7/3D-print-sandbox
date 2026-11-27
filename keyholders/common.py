"""What the key holders share: solid helpers, a wall keyhole, the 3MF writer
and a preview render. Every model is built in print orientation: back on the
bed (z = 0), x across, y up the wall, and things that stick out grow in +z.
"""
import zipfile
import numpy as np, trimesh
from trimesh.creation import box, cylinder

SCREW_HEAD, SCREW_SHANK = 9.0, 4.5

def hull(pts): return trimesh.convex.convex_hull(np.array(pts, float))
def u(ms): return trimesh.boolean.union(list(ms), engine="manifold")
def d(a, *bs): return trimesh.boolean.difference([a, *bs], engine="manifold")
def x_(a, b): return trimesh.boolean.intersection([a, b], engine="manifold")

def prism(pts_xy, z0, z1):
    """A convex outline in x, y, extruded from z0 to z1."""
    return hull([(x, y, z) for x, y in pts_xy for z in (z0, z1)])

def side_prism(pts_zy, x0, x1):
    """A convex side profile in z, y, extruded across from x0 to x1."""
    return hull([(x, y, z) for z, y in pts_zy for x in (x0, x1)])

def rounded_slab(x0, x1, y0, y1, z0, z1, r):
    pts = [(cx + r*np.cos(a), cy + r*np.sin(a))
           for cx in (x0 + r, x1 - r) for cy in (y0 + r, y1 - r)
           for a in np.linspace(0, 2*np.pi, 32, endpoint=False)]
    return prism(pts, z0, z1)

def keyhole(x, y, pocket=3):
    """Screw head goes in the round hole, the holder drops onto the slot.
    The pocket on the back lets the head sit behind the wall of the part."""
    def zcyl(r, cx, cy, z0, z1):
        c = cylinder(radius=r, height=z1 - z0, sections=48); c.apply_translation((cx, cy, (z0 + z1)/2)); return c
    return [zcyl(SCREW_HEAD/2, x, y, -1, 40),
            box(bounds=((x - SCREW_SHANK/2, y, -1), (x + SCREW_SHANK/2, y + 9, 40))),
            zcyl(SCREW_SHANK/2, x, y + 9, -1, 40),
            box(bounds=((x - SCREW_HEAD/2, y, -1), (x + SCREW_HEAD/2, y + 9, pocket))),
            zcyl(SCREW_HEAD/2, x, y + 9, -1, pocket)]

_TYPES = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
          '<Default Extension="config" ContentType="text/xml"/></Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')

def _esc(s): return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

_MATERIAL_NS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
_IDENTITY = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"

def write_3mf(parts, path, name):
    """One object per filament, grouped as one, each pointing at its colour.

    Colour alone does not get a part onto the right filament, and each slicer
    looks for it somewhere different, so the file says it three ways:

    * an ``m:colorgroup`` (3MF Materials extension) the objects point into,
      which is what Bambu Studio maps to filaments for a 3MF it did not write,
      and what plain 3MF viewers show. Core ``basematerials`` are ignored by
      Bambu and Orca, which is why the colours used to go missing;
    * ``Metadata/model_settings.config``, where Bambu Studio and Orca read a
      filament number per part;
    * ``Metadata/Slic3r_PE_model.config``, the same for PrusaSlicer, which
      loads each grouped part as an object of its own and so is told per
      part, each as one volume spanning its own triangles.
    """
    lo = np.min([m.bounds[0] for _, _, m in parts], axis=0)
    objs, ids = [], []
    for i, (pname, rgb, m) in enumerate(parts):
        oid = i + 2
        objs.append(f'<object id="{oid}" type="model" name="{_esc(pname)}" pid="1" pindex="{i}"><mesh><vertices>'
                    + "".join(f'<vertex x="{a:.6f}" y="{b:.6f}" z="{c:.6f}"/>' for a, b, c in m.vertices - lo)
                    + "</vertices><triangles>"
                    + "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
                    + "</triangles></mesh></object>")
        ids.append(oid)
    gid = len(parts) + 2
    objs.append(f'<object id="{gid}" type="model" name="{_esc(name)}"><components>'
                + "".join(f'<component objectid="{i}"/>' for i in ids) + "</components></object>")
    colours = "".join('<m:color color="#%02X%02X%02XFF"/>' % rgb for _, rgb, _ in parts)
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
             f'xmlns:m="{_MATERIAL_NS}">'
             f'<metadata name="Title">{_esc(name)}</metadata>'
             f'<resources><m:colorgroup id="1">{colours}</m:colorgroup>{"".join(objs)}</resources>'
             f'<build><item objectid="{gid}" transform="1 0 0 0 1 0 0 0 1 20 20 0"/></build></model>')

    # filament 1, 2, ... in the order the parts are listed, matching the colours
    bambu = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>", f'  <object id="{gid}">',
             f'    <metadata key="name" value="{_esc(name)}"/>', '    <metadata key="extruder" value="1"/>']
    prusa = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    for i, ((pname, _, m), oid) in enumerate(zip(parts, ids)):
        bambu += [f'    <part id="{oid}" subtype="normal_part">',
                  f'      <metadata key="name" value="{_esc(pname)}"/>',
                  f'      <metadata key="matrix" value="{_IDENTITY}"/>',
                  f'      <metadata key="extruder" value="{i + 1}"/>', "    </part>"]
        prusa += [f'  <object id="{oid}" instances_count="1">',
                  f'    <metadata type="object" key="name" value="{_esc(pname)}"/>',
                  f'    <metadata type="object" key="extruder" value="{i + 1}"/>',
                  f'    <volume firstid="0" lastid="{len(m.faces) - 1}">',
                  f'      <metadata type="volume" key="name" value="{_esc(pname)}"/>',
                  '      <metadata type="volume" key="volume_type" value="ModelPart"/>',
                  f'      <metadata type="volume" key="matrix" value="{_IDENTITY}"/>',
                  f'      <metadata type="volume" key="extruder" value="{i + 1}"/>', "    </volume>", "  </object>"]
    bambu += ["  </object>", "</config>"]
    prusa += ["</config>"]

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TYPES); z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/model_settings.config", "\n".join(bambu) + "\n")
        z.writestr("Metadata/Slic3r_PE_model.config", "\n".join(prusa) + "\n")

def report(parts):
    for name, _, m in parts:
        print(f"{name}: watertight={m.is_watertight} volume={m.volume/1000:.1f} cm3 faces={len(m.faces)}")
    if len(parts) > 1:
        ov = x_(parts[0][2], u(m for _, _, m in parts[1:]))
        print("overlap mm3:", round(ov.volume, 2) if len(ov.faces) else 0)
    print("size mm (x, y, z):", np.round(u(m for _, _, m in parts).extents, 1))

def preview(parts, path, azim=-60, elev=20):
    """Render it as it hangs on the wall: y up, sticking out toward the viewer.

    A small z-buffer rasteriser rather than matplotlib's 3D axes: matplotlib
    sorts whole triangles, so long faces (the floor) paint over flush inlays.
    `azim` and `elev` mean what they do in matplotlib's view_init.
    """
    from PIL import Image
    wall = trimesh.transformations.rotation_matrix(np.pi/2, (1, 0, 0))
    L = np.array([0.3, -0.8, 0.5]); L /= np.linalg.norm(L)
    tris, cols = [], []
    for _, rgb, m in parts:
        m = m.copy(); m.apply_transform(wall)
        shade = np.clip(m.face_normals @ L, 0.15, 1)[:, None]
        tris.append(m.triangles); cols.append(np.array(rgb, float)*(0.3 + 0.7*shade))
    tris, cols = np.concatenate(tris), np.concatenate(cols)

    a, e = np.radians(azim), np.radians(elev)
    eye = np.array([np.cos(e)*np.cos(a), np.cos(e)*np.sin(a), np.sin(e)])
    right = np.cross(-eye, (0, 0, 1)); right /= np.linalg.norm(right)
    up = np.cross(right, -eye)
    P = np.stack([tris @ right, tris @ up, tris @ eye], axis=-1)       # screen x, y, depth (bigger = nearer)

    SS, size, pad = 2, 900, 30                                         # 2x supersampled
    lo, hi = P[..., :2].reshape(-1, 2).min(0), P[..., :2].reshape(-1, 2).max(0)
    k = (size - 2*pad) / (hi - lo).max()
    w, h = ((hi - lo)*k + 2*pad).astype(int)
    P[..., 0] = (P[..., 0] - lo[0])*k*SS + pad*SS
    P[..., 1] = (hi[1] - P[..., 1])*k*SS + pad*SS
    W, H = w*SS, h*SS
    zbuf = np.full((H, W), -np.inf); img = np.full((H, W, 3), 255.0)
    for (p0, p1, p2), c in zip(P, cols):
        x0, x1 = int(max(min(p0[0], p1[0], p2[0]), 0)), int(min(max(p0[0], p1[0], p2[0]) + 1, W))
        y0, y1 = int(max(min(p0[1], p1[1], p2[1]), 0)), int(min(max(p0[1], p1[1], p2[1]) + 1, H))
        if x1 <= x0 or y1 <= y0:
            continue
        den = (p1[1] - p2[1])*(p0[0] - p2[0]) + (p2[0] - p1[0])*(p0[1] - p2[1])
        if abs(den) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        b0 = ((p1[1] - p2[1])*(gx - p2[0]) + (p2[0] - p1[0])*(gy - p2[1])) / den
        b1 = ((p2[1] - p0[1])*(gx - p2[0]) + (p0[0] - p2[0])*(gy - p2[1])) / den
        b2 = 1 - b0 - b1
        inside = (b0 >= -1e-6) & (b1 >= -1e-6) & (b2 >= -1e-6)
        z = b0*p0[2] + b1*p1[2] + b2*p2[2]
        zb = zbuf[y0:y1, x0:x1]
        hit = inside & (z > zb)
        zb[hit] = z[hit]; img[y0:y1, x0:x1][hit] = c
    img = img.reshape(h, SS, w, SS, 3).mean(axis=(1, 3))
    Image.fromarray(img.astype(np.uint8)).save(path)
