"""Tiny software renderer for the STL previews (no GPU / no display needed)."""
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def look_at(eye, target, up=(0, 0, 1)):
    f = np.array(target, float) - np.array(eye, float)
    f /= np.linalg.norm(f)
    up = np.array(up, float)
    s = np.cross(f, up); s /= np.linalg.norm(s)
    u = np.cross(s, f)
    return np.vstack([s, u, -f]), np.array(eye, float)


def render(mesh, path, size=760, elev=22.0, azim=35.0, zoom=1.18, bg=245):
    c = mesh.bounds.mean(axis=0)
    radius = np.linalg.norm(mesh.extents) / 2.0
    a, e = np.radians(azim), np.radians(elev)
    eye = c + radius * 4.0 * np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    R, eye = look_at(eye, c)

    v = (np.asarray(mesh.vertices) - eye) @ R.T
    scale = size / (2.0 * radius) * zoom
    px = np.column_stack([v[:, 0] * scale + size / 2.0, size / 2.0 - v[:, 1] * scale])
    depth = -v[:, 2]

    faces = np.asarray(mesh.faces)
    n = (np.asarray(mesh.vertices)[faces[:, 1]] - np.asarray(mesh.vertices)[faces[:, 0]])
    n = np.cross(n, np.asarray(mesh.vertices)[faces[:, 2]] - np.asarray(mesh.vertices)[faces[:, 0]])
    n /= (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
    key = np.array([0.45, 0.35, 0.82]); key /= np.linalg.norm(key)
    shade = np.clip(n @ key, 0, 1) ** 0.85 * 0.78 + 0.18
    spec = np.clip(n @ key, 0, 1) ** 28 * 0.5
    lum = np.clip(shade + spec, 0, 1)

    img = np.full((size, size), float(bg) / 255.0)
    zbuf = np.full((size, size), np.inf)
    P, D = px[faces], depth[faces]
    order = np.argsort(-D[:, 0])
    for fi in order:
        p, d, L = P[fi], D[fi], lum[fi]
        x0 = max(int(np.floor(p[:, 0].min())), 0); x1 = min(int(np.ceil(p[:, 0].max())), size - 1)
        y0 = max(int(np.floor(p[:, 1].min())), 0); y1 = min(int(np.ceil(p[:, 1].max())), size - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        det = ((p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1]))
        if abs(det) < 1e-9:
            continue
        l0 = ((p[1, 1] - p[2, 1]) * (xs - p[2, 0]) + (p[2, 0] - p[1, 0]) * (ys - p[2, 1])) / det
        l1 = ((p[2, 1] - p[0, 1]) * (xs - p[2, 0]) + (p[0, 0] - p[2, 0]) * (ys - p[2, 1])) / det
        l2 = 1.0 - l0 - l1
        m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not m.any():
            continue
        zz = l0 * d[0] + l1 * d[1] + l2 * d[2]
        yy, xx = ys[m], xs[m]
        closer = zz[m] < zbuf[yy, xx]
        yy, xx, zz = yy[closer], xx[closer], zz[m][closer]
        zbuf[yy, xx] = zz
        img[yy, xx] = L

    # screen-space edge darkening, so relief reads even in flat lighting
    z = np.where(np.isinf(zbuf), np.nan, zbuf)
    step = np.zeros_like(img)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        d = np.abs(z - np.roll(np.roll(z, dy, 0), dx, 1))
        step = np.maximum(step, np.nan_to_num(d))
    img = img * (1.0 - 0.55 * np.clip(step / (0.09 * radius), 0, 1))

    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path)
    return path


def half(mesh, axis=1):
    """Cut the mesh in half so the internal thread is visible."""
    return mesh.slice_plane(mesh.bounds.mean(axis=0), -np.eye(3)[axis], cap=True)


if __name__ == "__main__":
    out = ROOT / "previews"
    out.mkdir(exist_ok=True)
    for stl in sorted((ROOT / "stl").glob("*.stl")):
        m = trimesh.load(stl)
        render(m, out / f"{stl.stem}.png")
        render(m, out / f"{stl.stem}_top.png", elev=72.0, azim=90.0, zoom=1.45)
        render(half(m), out / f"{stl.stem}_section.png", azim=55)
        print("rendered", stl.stem)
