"""3MFs in the form Bambu Studio saves them, so its family of slicers (Bambu
Studio, OrcaSlicer, Snapmaker Orca) open a multi-colour part with every colour
already on its own filament.

Those slicers only take the colours from a 3MF of their own kind: one object a
part, made of one component a colour, the meshes in 3D/Objects/, and
Metadata/model_settings.config naming each component (a "part") and its
extruder. A plain 3MF's base materials, or PrusaSlicer's
Metadata/Slic3r_PE_model.config, they read as one colour, on filament 1.

Every file here uses the same extruders, so the four spools are loaded once:

    1 navy   2 yellow   3 blue   4 white (or the light blue the traced logo
                                           uses, which never shares a part
                                           with white)
"""
import uuid
import zipfile
from xml.sax.saxutils import quoteattr

import numpy as np

EXTRUDER = {"#0b1424": 1, "#ffd23f": 2, "#2b7de0": 3, "#ffffff": 4, "#8cc4ff": 4}
NAMES = {"#0b1424": "Navy", "#ffd23f": "Yellow", "#2b7de0": "Blue", "#ffffff": "White", "#8cc4ff": "Light blue"}
APP = "BambuStudio-01.08.04.51"
CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
BBS = "http://schemas.bambulab.com/package/2021"
IDENTITY = "1 0 0 0 1 0 0 0 1 0 0 0"


def _uuid(n):
    return str(uuid.UUID(int=(0x5D11D << 96) + n))


def write(path, objects, cols=4, gap=8.0):
    """objects: [(name, [(hex, vertices, faces)])], each a colour of one printable object.
    Each object is centred on its own origin, its bottom at z 0, and set out on a grid,
    `cols` across; the slicer's Arrange puts them on its plates."""
    sizes = [np.ptp(np.vstack([v for _, v, _ in p])[:, :2], axis=0) for _, p in objects]
    cell = np.max(sizes, axis=0) + gap
    meshes, parents, items, config = [], [], [], []
    mid = 1
    pid = len([1 for _, p in objects for _ in p]) + 1
    for n, (name, pieces) in enumerate(objects):
        allv = np.vstack([v for _, v, _ in pieces])
        lo, hi = allv.min(0), allv.max(0)
        centre = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        comps, parts = [], []
        for hexc, v, f in sorted(pieces, key=lambda p: EXTRUDER[p[0]]):
            vv = v - centre
            vs = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in vv)
            ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f)
            meshes.append(f'<object id="{mid}" p:UUID="{_uuid(mid)}" type="model"><mesh><vertices>{vs}</vertices>'
                          f'<triangles>{ts}</triangles></mesh></object>')
            comps.append(f'<component p:path="/3D/Objects/object_1.model" objectid="{mid}" p:UUID="{_uuid(10000 + mid)}" transform="{IDENTITY}"/>')
            parts.append(f'    <part id="{mid}" subtype="normal_part">\n'
                         f'      <metadata key="name" value={quoteattr(f"{name} {NAMES[hexc]}")}/>\n'
                         f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                         f'      <metadata key="extruder" value="{EXTRUDER[hexc]}"/>\n'
                         f'    </part>\n')
            mid += 1
        x, y = (n % cols) * cell[0], -(n // cols) * cell[1]
        parents.append(f'<object id="{pid}" p:UUID="{_uuid(20000 + pid)}" type="model"><components>{"".join(comps)}</components></object>')
        items.append(f'<item objectid="{pid}" p:UUID="{_uuid(30000 + pid)}" transform="1 0 0 0 1 0 0 0 1 {x:.4f} {y:.4f} 0"/>')
        config.append(f'  <object id="{pid}">\n'
                      f'    <metadata key="name" value={quoteattr(name)}/>\n'
                      f'    <metadata key="extruder" value="1"/>\n' + "".join(parts) + '  </object>\n')
        pid += 1

    head = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" xmlns="{CORE}" '
            f'xmlns:BambuStudio="{BBS}" xmlns:p="{PROD}" requiredextensions="p">\n')
    main = (head + f' <metadata name="Application">{APP}</metadata>\n <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
            f' <resources>{"".join(parents)}</resources>\n <build p:UUID="{_uuid(40000)}">{"".join(items)}</build>\n</model>\n')
    sub = head + f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>{"".join(meshes)}</resources>\n <build/>\n</model>\n'
    rel = 'http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                   '<Default Extension="config" ContentType="text/xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="{rel}"/></Relationships>')
        z.writestr("3D/_rels/3dmodel.model.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Target="/3D/Objects/object_1.model" Id="rel-1" Type="{rel}"/></Relationships>')
        z.writestr("3D/3dmodel.model", main)
        z.writestr("3D/Objects/object_1.model", sub)
        z.writestr("Metadata/model_settings.config", '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(config) + '</config>\n')


def from_parts(parts, palette, slots):
    """cards' parts (each {"slots": {slot: mesh}}) and the palette in `slots` order, as
    write() takes them."""
    out = []
    for part in parts:
        label = " ".join(x for x in (part.get("label", ""), part.get("name", "")) if x) or "part"
        out.append((label, [(palette[slots.index(s)].lower(), np.asarray(m.vertices), np.asarray(m.faces))
                            for s, m in part["slots"].items()]))
    return out


def read(path):
    """A file write() made, back as [(name, [(hex, vertices, faces)])]: each part's colour is
    its extruder's (EXTRUDER; 4 reads as white unless the part's name says light blue)."""
    import xml.etree.ElementTree as ET
    ns = {"m": CORE}
    z = zipfile.ZipFile(path)
    sub = ET.fromstring(z.read("3D/Objects/object_1.model"))
    meshes = {}
    for o in sub.find("m:resources", ns).findall("m:object", ns):
        m = o.find("m:mesh", ns)
        v = np.array([[float(e.get(k)) for k in "xyz"] for e in m.find("m:vertices", ns)])
        f = np.array([[int(e.get(k)) for k in ("v1", "v2", "v3")] for e in m.find("m:triangles", ns)])
        meshes[o.get("id")] = (v, f)
    by_ext = {1: "#0b1424", 2: "#ffd23f", 3: "#2b7de0", 4: "#ffffff"}
    out = []
    for obj in ET.fromstring(z.read("Metadata/model_settings.config")).findall("object"):
        meta = lambda e, k: next((m.get("value") for m in e.findall("metadata") if m.get("key") == k), "")
        pieces = []
        for part in obj.findall("part"):
            hexc = "#8cc4ff" if meta(part, "name").endswith("Light blue") else by_ext[int(meta(part, "extruder"))]
            pieces.append((hexc, *meshes[part.get("id")]))
        out.append((meta(obj, "name"), pieces))
    return out
