"""Extract the flat 2D outline of the Honda emblem from the source .glb.

The source model is a thin, slightly domed emblem plate lying in the world YZ
plane.  We rotate it so the badge faces +Z, project the silhouette down onto
the XY plane, clean up a few stray slivers from the triangulation, and dump the
result as JSON (exterior ring + hole rings, centred on the bounding box, in
arbitrary "model units" -- generate.py rescales it to millimetres).

Usage:  python3 src/extract_outline.py path/to/honda_logo.glb
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import Polygon

# Holes smaller than this (in model units^2) are triangulation noise, not part
# of the logo.  The four real holes are all > 0.16.
MIN_HOLE_AREA = 5e-3
SIMPLIFY_TOL = 8e-4

OUT = Path(__file__).resolve().parent / "logo_outline.json"


def main(glb_path: str) -> None:
    scene = trimesh.load(glb_path)
    mesh = scene.to_geometry() if isinstance(scene, trimesh.Scene) else scene

    # +90 deg about Y: (x, y, z) -> (z, y, -x).  A proper rotation (det = +1),
    # so the emblem is not mirrored.
    rot = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
    mesh.vertices = np.asarray(mesh.vertices) @ rot.T

    poly = trimesh.path.polygons.projected(mesh, normal=[0, 0, 1])
    if poly is None:
        raise SystemExit("could not project the mesh silhouette")

    holes = [r for r in poly.interiors if Polygon(r).area > MIN_HOLE_AREA]
    poly = Polygon(poly.exterior, holes).buffer(0)
    poly = poly.simplify(SIMPLIFY_TOL, preserve_topology=True)

    minx, miny, maxx, maxy = poly.bounds
    poly = affinity.translate(poly, -(minx + maxx) / 2.0, -(miny + maxy) / 2.0)

    data = {
        "source": Path(glb_path).name,
        "width": poly.bounds[2] - poly.bounds[0],
        "height": poly.bounds[3] - poly.bounds[1],
        "exterior": [list(map(float, c)) for c in poly.exterior.coords],
        "holes": [[list(map(float, c)) for c in r.coords] for r in poly.interiors],
    }
    OUT.write_text(json.dumps(data, indent=1))
    print(f"{OUT}: {len(data['holes'])} holes, "
          f"{data['width']:.4f} x {data['height']:.4f} model units")


if __name__ == "__main__":
    main(sys.argv[1])
