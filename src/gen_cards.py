"""Write a realtor NFC card or keyring fob as a printable STL.

    python3 src/gen_cards.py --name "Jane Doe" \
                             --company "Bluewater Realty" \
                             --phone "(555) 214-8890"

writes stl/jane_doe_card.3mf and .stl, and the same for the fob.  The 3MF has
the body and the raised lettering as separate coloured parts, so the slicer
opens it already set up for two filaments; the STL is one welded solid plus a
colour-change height.  --preview also renders them.  src/app.py is the same
thing with a browser front end.

Measure your NFC tags and pass --tag WxH: the pocket is cut to fit, and the
fob grows if it has to.  Everything else worth changing lives in src/cards.py.
"""
import argparse
import re
from pathlib import Path

import cards

ROOT = Path(__file__).resolve().parent.parent


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "card"


def report(name, info):
    print(f"  {name:38s} {info['w']:5.1f} x {info['h']:5.1f} x {info['total_z']:4.1f} mm  "
          f"{info['volume']:5.2f} cm^3  "
          f"{'watertight' if info['watertight'] else 'NOT WATERTIGHT'}")
    for key, line in info["lines"].items():
        print(f"      {key:8s} {line['cap']:4.1f} mm caps, ~{line['stroke']:.2f} mm strokes")
    print(f"      mark     ~{info['mark_stroke']:.2f} mm strokes"
          + (f", tap text ~{info['tap_stroke']:.2f} mm" if info["tap_stroke"] else ""))
    print(f"      pocket   {info['pocket'][0]:.1f} x {info['pocket'][1]:.1f} x "
          f"{info['pocket'][2]:.1f} mm deep ({info['tag_mode']})")
    if info["tag_mode"] == "split":
        print(f"      assembly two halves, {info['part_thick']:.1f} mm each including the "
              f"relief, {info['pins']} register pins -- {info['assembled']:.1f} mm glued up "
              f"with the tag between them")
    if info["thin"]:
        print(f"      note     {', '.join(info['thin'])} under {cards.MIN_STROKE} mm -- "
              f"turn on the slicer's thin-wall detection, or shorten the text")
    if info["pause_z"] is not None:
        print(f"      pause    the print at Z = {info['pause_z']:.2f} mm and drop the tag in")
    changes = " and ".join(f"Z = {z:.2f} mm" for z in info["changes"])
    print(f"      colour   change filament at {changes}"
          + (" (each half)" if info["tag_mode"] == "split" else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="", help="the realtor's name, the big line")
    ap.add_argument("--company", default="", help="brokerage, under the name")
    ap.add_argument("--phone", default="", help="phone number, under the rule")
    ap.add_argument("--kind", default="both", choices=["card", "fob", "both"])
    ap.add_argument("--tag", default=None, metavar="WxH",
                    help=f"NFC tag size in mm (default "
                         f"{cards.TAG['w']:g}x{cards.TAG['h']:g})")
    ap.add_argument("--tag-thick", type=float, default=cards.TAG["thick"],
                    help="NFC tag thickness in mm")
    ap.add_argument("--tag-mode", default="pocket", choices=["pocket", "embed", "split"],
                    help="pocket: open recess, drop the tag in afterwards.  "
                         "embed: roofed over, pause the print and bury it.  "
                         "split: two halves to glue with the tag between them")
    ap.add_argument("--tap", default="TAP HERE",
                    help="wording under the contactless mark; '|' splits lines, "
                         "empty leaves just the arcs")
    ap.add_argument("--rise", type=float, default=cards.RISE,
                    help=f"how far the lettering stands off the face, mm "
                         f"(default {cards.RISE:g})")
    ap.add_argument("--colours", default="#cfd3d6,#d9a441", metavar="BODY,RAISED",
                    help="hex colours written into the 3MF, body then raised")
    ap.add_argument("--format", default="both", choices=["3mf", "stl", "both"])
    ap.add_argument("--no-border", action="store_true", help="drop the raised card border")
    ap.add_argument("--font", default=None, help="path to a TTF; a bold sans works best")
    ap.add_argument("--out", default=str(ROOT / "stl"), help="where to write the STLs")
    ap.add_argument("--preview", action="store_true", help="also render PNGs to previews/")
    args = ap.parse_args()

    if not any([args.name, args.company, args.phone]):
        ap.error("give at least one of --name / --company / --phone")

    tag = dict(thick=args.tag_thick)
    if args.tag:
        try:
            tag["w"], tag["h"] = (float(v) for v in args.tag.lower().split("x"))
        except ValueError:
            ap.error(f"--tag wants WxH in mm, e.g. 35x22 -- got {args.tag!r}")

    colours = tuple(c.strip() for c in args.colours.split(","))
    if len(colours) != 2 or not all(re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colours):
        ap.error(f"--colours wants two hex colours like #cfd3d6,#d9a441 -- got {args.colours!r}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    kinds = ["card", "fob"] if args.kind == "both" else [args.kind]
    print("building:")
    for kind in kinds:
        parts, info = cards.build(
            kind, args.name, args.company, args.phone, font=args.font, tag=tag,
            tap_text=args.tap, tag_mode=args.tag_mode, border=not args.no_border,
            rise=args.rise)
        stem = f"{slug(args.name or args.company)}_{kind}"
        names, written = [], []
        for part in parts:
            names.append(f"{stem}_{part['name']}" if part["name"] else stem)
            if args.format != "3mf":
                part["mesh"].export(out / f"{names[-1]}.stl")
                written.append(f"{names[-1]}.stl")
        if args.format != "stl":
            (out / f"{stem}.3mf").write_bytes(cards.export_3mf(parts, colours))
            written.insert(0, f"{stem}.3mf")
        report(", ".join(written), info)
        if args.preview:
            import numpy as np
            import trimesh
            import render
            shots = ROOT / "previews"
            shots.mkdir(exist_ok=True)
            for name, part in zip(names, (p["mesh"] for p in parts)):
                flipped = part.copy()
                flipped.apply_transform(
                    trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0]))
                render.render(flipped, shots / f"{name}_front.png",
                              elev=58, azim=-90, zoom=1.04)
                render.render(part, shots / f"{name}_back.png",
                              elev=58, azim=-90, zoom=1.04)


if __name__ == "__main__":
    main()
