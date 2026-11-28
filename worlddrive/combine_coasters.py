"""Every four-colour coaster in one 3MF: worlddrive/stl/wd_all_coasters.3mf.

    python3 worlddrive/combine_coasters.py

Reads each coaster's own 3MF (designs.py and infill_coasters.py make them, in
cards.export_3mf_tools' form) and lays them out on a grid, four across, each its
own object with each colour a part already on its extruder, the same four for
all of them: 1 navy, 2 yellow, 3 blue, 4 white. So the slicer (Snapmaker's, or
any Orca or PrusaSlicer) opens it in colour, the four filaments loaded once.

The logo coaster (wd_coaster_logo) isn't in it: its continents are a fifth
colour, light blue, and the printer holds four. It prints from its own file.
Run this again after rebuilding any of them.
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import quoteattr

import numpy as np

HERE = Path(__file__).resolve().parent
NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
# The extruders, in order, for every coaster in the file.
FILAMENTS = [("#0b1424", "Navy"), ("#ffd23f", "Yellow"), ("#2b7de0", "Blue"), ("#ffffff", "White")]
MATERIAL = "PETG"
COASTERS = [f"wd_infill_{p}{s}" for s in ("_logo", "") for p in ("topo", "honeycomb", "gyroid", "globe")] + [
    "wd_coaster_badge", "wd_coaster_mark"]


def read(path):
    """A coaster's 3MF (export_3mf_tools' form) as [(hex, vertices, faces)], one a colour,
    in the file's own placing."""
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("3D/3dmodel.model"))
    colours = re.search(r"filament_colour = (.*)", z.read("Metadata/Slic3r_PE.config").decode()).group(1)
    colours = [c.strip().lower() for c in colours.split(";")]
    config = ET.fromstring(z.read("Metadata/Slic3r_PE_model.config"))
    obj = root.find("m:resources", NS).find("m:object", NS)
    item = root.find("m:build", NS).find("m:item", NS)
    off = np.array([float(x) for x in item.get("transform").split()[9:12]])
    mesh = obj.find("m:mesh", NS)
    v = np.array([[float(e.get(k)) for k in "xyz"] for e in mesh.find("m:vertices", NS)]) + off
    f = np.array([[int(e.get(k)) for k in ("v1", "v2", "v3")] for e in mesh.find("m:triangles", NS)])
    pieces = []
    for vol in config.find("object").findall("volume"):
        ext = int(next(m.get("value") for m in vol.findall("metadata") if m.get("key") == "extruder"))
        tris = f[int(vol.get("firstid")):int(vol.get("lastid")) + 1]
        used = np.unique(tris)
        remap = np.full(len(v), -1)
        remap[used] = np.arange(len(used))
        pieces.append((colours[ext - 1], v[used], remap[tris]))
    return pieces


def write(coasters, path, cols=4, gap=8.0):
    order = [c for c, _ in FILAMENTS]
    sizes = [np.ptp(np.vstack([v for _, v, _ in p])[:, :2], axis=0) for _, p in coasters]
    cell = np.max(sizes, axis=0) + gap
    objects, items, configs = [], [], []
    for oid, (name, pieces) in enumerate(coasters, start=1):
        allv = np.vstack([v for _, v, _ in pieces])
        lo, hi = allv.min(0), allv.max(0)
        at = np.array([(oid - 1) % cols * cell[0], -((oid - 1) // cols) * cell[1], 0.0])
        shift = at - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        verts, tris, volumes, nv, nt = [], [], [], 0, 0
        for hexc, v, f in sorted(pieces, key=lambda p: order.index(p[0])):
            verts.append("".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in v + shift))
            tris.append("".join(f'<triangle v1="{a + nv}" v2="{b + nv}" v3="{c + nv}"/>' for a, b, c in f))
            label = f"{dict(FILAMENTS)[hexc]} {MATERIAL}"
            volumes.append(f' <volume firstid="{nt}" lastid="{nt + len(f) - 1}">\n'
                           f'  <metadata type="volume" key="name" value={quoteattr(label)}/>\n'
                           f'  <metadata type="volume" key="volume_type" value="ModelPart"/>\n'
                           f'  <metadata type="volume" key="extruder" value="{order.index(hexc) + 1}"/>\n'
                           f' </volume>\n')
            nv += len(v)
            nt += len(f)
        objects.append(f'<object id="{oid}" type="model" name={quoteattr(name)}><mesh><vertices>{"".join(verts)}</vertices>'
                       f'<triangles>{"".join(tris)}</triangles></mesh></object>')
        items.append(f'<item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
        configs.append(f'<object id="{oid}" instances_count="1">\n <metadata type="object" key="name" value={quoteattr(name)}/>\n'
                       f' <metadata type="object" key="extruder" value="1"/>\n' + "".join(volumes) + '</object>\n')
    colours = ";".join(c.upper() for c in order)
    project = "".join(f"; {k} = {v}\n" for k, v in (
        ("extruder_colour", colours), ("filament_colour", colours),
        ("filament_type", ";".join([MATERIAL] * len(order))),
        ("filament_settings_id", ";".join(f'"{n} {MATERIAL}"' for _, n in FILAMENTS)),
        ("support_material", 0)))
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">'
             f'<metadata name="slic3rpe:Version3mf">1</metadata><resources>{"".join(objects)}</resources>'
             f'<build>{"".join(items)}</build></model>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '<Default Extension="config" ContentType="text/plain"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/Slic3r_PE_model.config", "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<config>\n" + "".join(configs) + "</config>\n")
        z.writestr("Metadata/Slic3r_PE.config", project)


if __name__ == "__main__":
    stl = HERE / "stl"
    coasters = [(name, read(stl / f"{name}.3mf")) for name in COASTERS]
    write(coasters, stl / "wd_all_coasters.3mf")
    print(len(coasters), "coasters, extruders", [n for _, n in FILAMENTS])
