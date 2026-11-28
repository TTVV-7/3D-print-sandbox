"""Every coaster in one 3MF: worlddrive/stl/wd_all_coasters.3mf.

    python3 worlddrive/combine_coasters.py

Reads each coaster's own 3MF (designs.py and infill_coasters.py make them) and
lays them out on a grid, four across, each its own object with its colours, the
materials merged (navy, yellow, blue, white and the logo coaster's light blue).
Run it again after rebuilding any of them.
"""
import zipfile
import xml.etree.ElementTree as ET
import numpy as np

NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
NAMES = {"#0b1424": "Navy", "#2b7de0": "Blue", "#ffd23f": "Yellow", "#ffffff": "White", "#8cc4ff": "Light blue"}

def read(path):
    """[(name, [(hex, vertices, faces)])], one entry per build item."""
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("3D/3dmodel.model"))
    res = root.find("m:resources", NS)
    bases = [b.get("displaycolor").lower()[:7] for b in res.find("m:basematerials", NS)]
    objs = {o.get("id"): o for o in res.findall("m:object", NS)}
    out = []
    for item in root.find("m:build", NS).findall("m:item", NS):
        t = [float(x) for x in item.get("transform", "1 0 0 0 1 0 0 0 1 0 0 0").split()]
        off = np.array(t[9:12])
        top = objs[item.get("objectid")]
        comps = top.find("m:components", NS)
        ids = [c.get("objectid") for c in comps] if comps is not None else [top.get("id")]
        pieces = []
        for i in ids:
            o = objs[i]
            mesh = o.find("m:mesh", NS)
            v = np.array([[float(e.get(k)) for k in "xyz"] for e in mesh.find("m:vertices", NS)]) + off
            f = np.array([[int(e.get(k)) for k in ("v1", "v2", "v3")] for e in mesh.find("m:triangles", NS)])
            pieces.append((bases[int(o.get("pindex", 0))], v, f))
        out.append((top.get("name") or path, pieces))
    return out

def write(coasters, path, cols=4, gap=8.0):
    colours = []
    for _, pieces in coasters:
        for hexc, _, _ in pieces:
            if hexc not in colours:
                colours.append(hexc)
    objects, items, oid = [], [], 2
    # one grid cell per coaster, the biggest coaster's size
    sizes = [np.ptp(np.vstack([v for _, v, _ in p])[:, :2], axis=0) for _, p in coasters]
    cell = np.max(sizes, axis=0) + gap
    for n, (name, pieces) in enumerate(coasters):
        allv = np.vstack([v for _, v, _ in pieces])
        lo, hi = allv.min(0), allv.max(0)
        centre = np.array([(n % cols) * cell[0], -(n // cols) * cell[1], 0.0])
        shift = centre - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        ids = []
        for hexc, v, f in pieces:
            vv = v + shift
            vs = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in vv)
            ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f)
            objects.append(f'<object id="{oid}" type="model" name="{name} {NAMES.get(hexc, hexc)}" pid="1" pindex="{colours.index(hexc)}">'
                           f'<mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>')
            ids.append(oid); oid += 1
        comps = "".join(f'<component objectid="{i}"/>' for i in ids)
        objects.append(f'<object id="{oid}" type="model" name="{name}"><components>{comps}</components></object>')
        items.append(f'<item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
        oid += 1
    bases = "".join(f'<base name="{NAMES.get(c, c)}" displaycolor="{c.upper()}"/>' for c in colours)
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<resources><basematerials id="1">{bases}</basematerials>{"".join(objects)}</resources>'
             f'<build>{"".join(items)}</build></model>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types); z.writestr("_rels/.rels", rels); z.writestr("3D/3dmodel.model", model)
    return colours

COASTERS = [f"wd_infill_{p}{s}" for s in ("_logo", "") for p in ("topo", "honeycomb", "gyroid", "globe")] + [
    "wd_coaster_badge", "wd_coaster_mark", "wd_coaster_logo"]

if __name__ == "__main__":
    from pathlib import Path
    stl = Path(__file__).resolve().parent / "stl"
    coasters = [(name, read(stl / f"{name}.3mf")[0][1]) for name in COASTERS]
    colours = write(coasters, stl / "wd_all_coasters.3mf")
    print(len(coasters), "coasters;", [NAMES.get(c, c) for c in colours])
