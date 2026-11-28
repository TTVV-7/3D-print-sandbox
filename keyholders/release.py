"""Build the files to post the bucket key holder (MakerWorld, Snapmaker's
model site, Printables...): for each branding, a 3MF per print option with
walls and infill already set, STLs, and a 4:3 cover plus views.

Run: python3 keyholders/release.py     -> keyholders/release/
"""
import os, runpy, shutil
import numpy as np, trimesh
from PIL import Image

from common import write_3mf, preview, u

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "release")

# branding: name -> (big lettering on the back wall, line under it)
VARIANTS = {"swc": ("SWC", "SOUTHWEST CONTRACTING"),
            "plain": ("KEYS", "DIG IN. HANG ON.")}

# print options. Part settings are per part: (yellow bucket, black teeth + edge + art)
OPTIONS = {
    "standard": dict(settings=dict(walls=4, infill=20, pattern="gyroid", top=5, bottom=4), parts=None),
    # the teeth and edge plate printed solid: that's where it breaks, and it's a small part of the print
    "strong": dict(settings=dict(walls=6, infill=40, pattern="gyroid", top=6, bottom=5), parts=[None, dict(infill=100)]),
}

VIEWS = {"cover": (-55, 25), "front": (-88, 8), "side": (-5, 10), "top": (-90, 80), "under": (-90, -80)}
BG = (244, 243, 239)


def framed(src, dst, size=(1600, 1200)):
    """Put a render on a plain 4:3 background, centred with a margin."""
    im = Image.open(src).convert("RGB")
    a = np.asarray(im).copy()
    a[(a == 255).all(-1)] = BG                                   # the renderer's background is pure white
    im = Image.fromarray(a)
    k = min(size[0]*0.86/im.width, size[1]*0.86/im.height)
    im = im.resize((int(im.width*k), int(im.height*k)), Image.LANCZOS)
    canvas = Image.new("RGB", size, BG)
    canvas.paste(im, ((size[0] - im.width)//2, (size[1] - im.height)//2))
    canvas.save(dst, optimize=True)


def build(variant):
    logo, tagline = VARIANTS[variant]
    os.environ["BUCKET_LOGO"], os.environ["BUCKET_TAGLINE"] = logo, tagline
    ns = runpy.run_path(os.path.join(HERE, "make_bucket.py"), run_name="release")
    parts = ns["parts"]
    d = os.path.join(OUT, variant); os.makedirs(os.path.join(d, "stl"), exist_ok=True)
    os.makedirs(os.path.join(d, "images"), exist_ok=True)
    base = f"excavator-bucket-key-holder_{variant}"
    for opt, o in OPTIONS.items():
        write_3mf(parts, os.path.join(d, f"{base}_{opt}.3mf"), f"Excavator bucket key holder ({logo}, {opt})",
                  settings=o["settings"], part_settings=o["parts"])
    yellow, black = parts[0][2], parts[1][2]
    yellow.export(os.path.join(d, "stl", f"{base}_yellow.stl"))
    black.export(os.path.join(d, "stl", f"{base}_black.stl"))
    u([yellow, black]).export(os.path.join(d, "stl", f"{base}_single-colour.stl"))
    tmp = os.path.join(d, "images", "_tmp.png")
    for name, (az, el) in VIEWS.items():
        preview(parts, tmp, azim=az, elev=el)
        framed(tmp, os.path.join(d, "images", f"{base}_{name}.png"))
    os.remove(tmp)
    print(variant, "done:", sorted(os.listdir(d)))


if __name__ == "__main__":
    shutil.rmtree(OUT, ignore_errors=True)
    for v in VARIANTS:
        build(v)
