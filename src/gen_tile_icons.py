"""The shape tiles' 3D icons: each product, rendered, as a strip of frames.

    python3 src/gen_tile_icons.py          # writes public/assets/tiles/*.webp

Each icon is the real thing -- the fob, the keyring, the pet tag on its split
ring, the sign, the stencil -- built by its own generator, lit the way the
pet tag's product shot is, and rendered at FRAMES angles as it sways.  The
page shows the first frame as the icon, and on hover steps through the rest
with a CSS animation.  So the tiles get a turning 3D object with no 3D
engine on the page for them at all: five small images, and nothing to load
before the form works.

Regenerating needs Node and Playwright (`npm i -g playwright`), because the
frames are rendered with the same three.js the product shot uses -- run
src/tile_icons_render.js through it.  The images are committed; the site
does not run this.
"""
import base64
import io
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

import cards
import nametag
import pettag
import signbox
import stencil

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "assets" / "tiles"
RENDER = Path(__file__).resolve().parent / "tile_icons_render.js"

# One frame, at twice the size it is shown (60 x 48 CSS px), for sharp screens.
W, H = 120, 96
FRAMES = 24
SWAY = 0.55          # radians either side of straight on

# What each tile shows, and in which colours: slot -> hex, in cards.SLOTS order
# (body, pattern, primary, secondary).  `glow` slots are lit from inside --
# the sign's letters.
ICONS = {
    "fob":     dict(build=lambda: cards.build("fob", name="Jane Doe",
                                              company="Bluewater Realty",
                                              phone="(555) 214-8890", tag_mode="pocket"),
                    colours=("#1f3a5f", "#2a4a75", "#f4f4f1", "#f2c14e")),
    "name":    dict(build=lambda: nametag.build("Ruby"),
                    colours=("#1f3a5f", "#1f3a5f", "#f2c14e", "#f2c14e")),
    "pet":     dict(build=lambda: pettag.build("Biscuit", phone="(555) 214-8890",
                                               shape="bone"),
                    colours=("#1f3a5f", "#f2c14e", "#f4f4f1", "#f2c14e"), ring=True),
    "sign":    dict(build=lambda: signbox.build("OPEN", lid=False),
                    colours=("#2b2f36", "#2b2f36", "#fff1c9", "#fff1c9"), glow=("primary",)),
    "stencil": dict(build=lambda: stencil.build("SHOP"),
                    colours=("#e0a100", "#e0a100", "#e0a100", "#e0a100")),
}


def glb(parts, info, colours, glow=(), ring=False):
    """The first part as a GLB, standing up: y up, its front towards +z."""
    if ring:
        return pettag.product_glb(parts[:1], info, colours)
    part = parts[0]
    scene = trimesh.Scene()
    turn = np.eye(4)
    if not info.get("front_up", True):          # built face down: turn it over
        turn = trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0])
    meshes = {}
    for slot, mesh in part["slots"].items():
        m = mesh.copy()
        m.apply_transform(turn)
        meshes[slot] = m
    lo = np.min([m.bounds[0] for m in meshes.values()], axis=0)
    hi = np.max([m.bounds[1] for m in meshes.values()], axis=0)
    for slot, m in meshes.items():
        m.apply_translation(-(lo + hi) / 2.0)
        colour = pettag.linear_rgba(colours[cards.SLOTS.index(slot)])
        m.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            name=slot, baseColorFactor=colour, metallicFactor=0.0, roughnessFactor=0.45,
            emissiveFactor=colour[:3] if slot in glow else None))
        scene.add_geometry(m, node_name=slot, geom_name=slot)
    buf = io.BytesIO()
    buf.write(scene.export(file_type="glb"))
    return buf.getvalue()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        jobs = []
        for name, icon in ICONS.items():
            parts, info = icon["build"]()
            path = Path(tmp) / f"{name}.glb"
            path.write_bytes(glb(parts, info, icon["colours"], icon.get("glow", ()),
                                 icon.get("ring", False)))
            jobs.append(dict(name=name, glb=str(path)))
            print(f"built {name}: {path.stat().st_size // 1024} kB")
        spec = dict(jobs=jobs, w=W, h=H, frames=FRAMES, sway=SWAY)
        out = subprocess.run(["node", str(RENDER)], input=json.dumps(spec), text=True,
                             capture_output=True, check=True)
        frames = json.loads(out.stdout)

    for name, shots in frames.items():
        strip = Image.new("RGBA", (W * len(shots), H), (0, 0, 0, 0))
        for i, shot in enumerate(shots):
            png = base64.b64decode(shot.split(",", 1)[1])
            strip.paste(Image.open(io.BytesIO(png)).convert("RGBA"), (i * W, 0))
        path = OUT / f"{name}.webp"
        strip.save(path, "WEBP", quality=88, method=6)
        print(f"wrote {path.relative_to(ROOT)}: {len(shots)} frames, "
              f"{path.stat().st_size // 1024} kB")


if __name__ == "__main__":
    main()
