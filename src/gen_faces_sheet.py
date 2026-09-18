"""Set one name in every face, as the keyring, for previews/keyring_faces.png.

The README's picture of the faces is not a font specimen: it is forty-eight
actual keyrings, built by nametag.build and rendered straight down, so what the
picture shows is the plastic -- the outline round the word, the ring tab, the
counters that survived the weld and the ones that did not.

Each face is set at the height it asks for, which is `min_cap` where that is
taller than the keyring's own default and the default otherwise.  A face that
still shuts counters at that height says so under its name; that is the whole
reason for setting them all at their own floor rather than all at one height.

    python3 src/gen_faces_sheet.py              # rewrites the preview
    python3 src/gen_faces_sheet.py sans slab    # just those, for a look

Like gen_specimens.py this is a build-time script: re-run it after adding a
face to typefaces.FACES.  The hosted function never touches it.
"""
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

import nametag
import render
import typefaces

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "previews" / "keyring_faces.png"

NAME = "Freddie"            # the name every face is set in
COLS = 3
CELL_W = 640                # px per column
IMG_H = 150                 # px of keyring above the labels
LABEL_H = 52                # px of labels below it
PAD = 16
BG = (245, 245, 245)

# Body dark, lettering light: the two-colour reading the sheet is drawn in.
COLOURS = ("#141414", "#2e2e2e", "#f2f2f2", "#9a9a9a")

FONT_DIR = Path(__file__).resolve().parent / "fonts"
LABEL_FONT = FONT_DIR / "LiberationSans-Bold.ttf"


def keyring(key, tmp):
    """One face, rendered straight down, cropped to the plastic.

    Returns (image, caption, subcaption).
    """
    spec = typefaces.FACES[key]
    cap = max(nametag.CAP, spec["min_cap"])
    parts, info = nametag.build(NAME, font=key, cap=cap)
    mesh, face_colours = render.coloured(parts, COLOURS)
    png = tmp / f"{key}.png"
    render.render(mesh, str(png), size=760, elev=90, azim=-90, zoom=1.02,
                  bg=BG, colours=face_colours)

    im = Image.open(png).convert("RGB")
    # Crop to what was actually drawn: the renders are square and the words
    # are not, so a fixed crop would shrink a long name and float a short one.
    bg = Image.new("RGB", im.size, BG)
    box = ImageChops.difference(im, bg).getbbox()
    if box:
        im = im.crop(box)

    shut = info.get("shut") or 0
    sub = f"{cap:g} mm" + (f", {shut} counters shut" if shut else "")
    return im, f'{spec["label"]} — {spec["font"]}', sub


def fit(im, w, h):
    """Scale to fit the cell without ever blowing a small keyring up."""
    k = min(w / im.width, h / im.height, 1.0)
    if k < 1.0:
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))),
                       Image.LANCZOS)
    return im


def sheet(keys):
    rows = (len(keys) + COLS - 1) // COLS
    row_h = IMG_H + LABEL_H
    W, H = CELL_W * COLS, row_h * rows + PAD
    page = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(page)
    big = ImageFont.truetype(str(LABEL_FONT), 19)
    small = ImageFont.truetype(str(LABEL_FONT), 15)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i, key in enumerate(keys):
            im, cap_txt, sub_txt = keyring(key, tmp)
            im = fit(im, CELL_W - 2 * PAD, IMG_H)
            cx = (i % COLS) * CELL_W + CELL_W // 2
            top = (i // COLS) * row_h
            page.paste(im, (cx - im.width // 2, top + (IMG_H - im.height) // 2))
            y = top + IMG_H + 4
            draw.text((cx, y), cap_txt, font=big, fill=(26, 26, 26), anchor="ma")
            draw.text((cx, y + 24), sub_txt, font=small, fill=(120, 120, 120),
                      anchor="ma")
            print(f"  {key:10} {cap_txt}  ({sub_txt})")
    return page


def main(argv):
    keys = [a for a in argv if a in typefaces.FACES] or list(typefaces.FACES)
    print(f"setting {NAME!r} in {len(keys)} faces:")
    page = sheet(keys)
    OUT.parent.mkdir(exist_ok=True)
    page.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)} ({page.width}x{page.height})")


if __name__ == "__main__":
    main(sys.argv[1:])
