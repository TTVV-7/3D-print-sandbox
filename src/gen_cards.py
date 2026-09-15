"""Write a realtor NFC card or keyring fob as a printable STL.

    python3 src/gen_cards.py --name "Jane Doe" \
                             --company "Bluewater Realty" \
                             --phone "(555) 214-8890"

writes stl/jane_doe_fob.3mf and .stl -- two halves to glue with the tag between
them, by default.  The 3MF has every colour as a separate part, so the slicer
opens it already set up for four filaments; the STL is one welded solid.
--preview also renders them.  src/app.py is the same thing with a browser
front end.

Measure your NFC tags and pass --tag WxH: the pocket is cut to fit, and the
fob grows if it has to.  Everything else worth changing lives in src/cards.py.
"""
import argparse
import re
from pathlib import Path

import cards
import looks
import nametag
import typefaces

ROOT = Path(__file__).resolve().parent.parent


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "card"


def report_name(name, info):
    print(f"  {name:38s} {info['w']:5.1f} x {info['h']:5.1f} x {info['total_z']:4.1f} mm  "
          f"{info['volume']:5.2f} cm^3  "
          f"{'watertight' if info['watertight'] else 'NOT WATERTIGHT'}")
    print(f"      face     {info['typeface_name']}"
          + (f" ({info['typeface']})" if info["typeface"] else ""))
    print(f"      letters  {info['cap']:.1f} mm caps on a {info['thick']:.1f} mm body, "
          f"{info['rise']:.1f} mm proud")
    print(f"      outline  {info['weld']:.2f} mm round the word"
          + (f", {info['bridges']} bridge(s) to hold the loose pieces on"
             if info["bridges"] else ""))
    if info["ring"]:
        print(f"      ring     {info['ring_d']:.1f} mm hole")
    if info["counter"]:
        print(f"      counters {info['counters']}, smallest {info['counter']:.2f} mm across")
    if info["shut"]:
        print(f"      filled   {info['shut']} counter(s) welded shut"
              + (f" -- this face wants {info['min_cap']:.0f} mm caps or more"
                 if info["min_cap"] else " -- raise the letter height"))
    elif info["thin"]:
        print(f"      note     {', '.join(info['thin'])} tight -- raise the letter height")
    if info["rise"]:
        print(f"      colour   change filament at Z = {info['thick']:.2f} mm")


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
              f"face, {info['pins']} register pins -- {info['assembled']:.1f} mm glued up "
              f"with the tag between them")
    if info["layout"]:
        print(f"      layout   {info['layout']}")
    if info["look"]:
        print(f"      pattern  {info['look']}, ~{info['pattern_stroke']:.2f} mm strokes")
    if info["logo"]:
        L = info["logo"]
        print(f"      {'design' if L.get('design') else 'logo':8s} {L['w']:.1f} x {L['h']:.1f} mm, "
              f"finest detail ~{L['detail']:.2f} mm")
    if info["qr"]:
        Q = info["qr"]
        print(f"      qr       {Q['modules']} modules at {Q['module']:.2f} mm, "
              f"{Q['size']:.1f} mm square")
    if info["logo"] or info["qr"]:
        print(f"      nozzle   " + (f"{info['nozzle']:.2f} mm or finer" if info["nozzle"]
                                   else "none prints this cleanly -- shorter link, or a "
                                        "simpler logo"))
    if info["thin"]:
        print(f"      note     {', '.join(info['thin'])} under {cards.MIN_STROKE} mm -- "
              f"turn on the slicer's thin-wall detection, or shorten the text")
    if info["pause_z"] is not None:
        print(f"      pause    the print at Z = {info['pause_z']:.2f} mm and drop the tag in")
    bands = " and ".join(f"Z = {a:.2f}-{b:.2f} mm" for a, b in info["colour_bands"])
    print(f"      colours  {len(info['slots'])} ({', '.join(info['slots'])}), all within "
          f"{bands}" + (" of each half" if info["tag_mode"] == "split" else "")
          + "; the body colour alone elsewhere")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="", help="the realtor's name, the big line")
    ap.add_argument("--company", default="", help="brokerage, under the name")
    ap.add_argument("--phone", default="", help="phone number, under the rule")
    ap.add_argument("--role", default="", help="the line under the name, or the slogan "
                                               "under the company -- layouts that have "
                                               "room for one")
    ap.add_argument("--email", default="", help="address along the bottom of the layouts "
                                                "that have a place for one")
    ap.add_argument("--layout", default=None, choices=list(cards.LAYOUTS),
                    help="where the fields go on the front (default: the look's own)")
    ap.add_argument("--logo-box", dest="placeholder", action="store_const", const="box",
                    help="draw an empty square where the logo would go")
    ap.add_argument("--kind", default="fob", choices=["card", "fob", "both", "name"],
                    help="fob and card carry an NFC tag; name is the keyring that is "
                         "just the word, welded into one piece")
    ap.add_argument("--cap", type=float, default=None,
                    help=f"letter height for --kind name, mm (default {nametag.CAP:g}, "
                         f"or the face's own minimum where that is taller)")
    ap.add_argument("--ring", type=float, default=nametag.RING_D,
                    help=f"ring hole for --kind name, mm; 0 drops the tab "
                         f"(default {nametag.RING_D:g})")
    ap.add_argument("--flat", action="store_true",
                    help="for --kind name: one solid in the body colour, no raised letters")
    ap.add_argument("--tag", default=None, metavar="WxH",
                    help=f"NFC tag size in mm (default "
                         f"{cards.TAG['w']:g}x{cards.TAG['h']:g})")
    ap.add_argument("--tag-thick", type=float, default=cards.TAG["thick"],
                    help="NFC tag thickness in mm")
    ap.add_argument("--tag-mode", default="split", choices=["split", "pocket", "embed"],
                    help="split: two halves to glue with the tag between them (default).  "
                         "pocket: open recess, drop the tag in afterwards.  "
                         "embed: roofed over, pause the print and bury it")
    ap.add_argument("--tap", default="TAP HERE",
                    help="wording under the contactless mark; '|' splits lines, "
                         "empty leaves just the arcs")
    ap.add_argument("--rise", type=float, default=None,
                    help=f"how far the lettering stands off the face, mm; 0 is flush "
                         f"(default {cards.RISE:g} on a card or fob, where the colours "
                         f"live in the face, and {nametag.RISE:g} on a name keyring, "
                         f"where the letters sit on top)")
    ap.add_argument("--look", default=looks.DEFAULT,
                    choices=list(looks.PRESETS) + [k for k in looks.PATTERNS
                                                   if k not in looks.PRESETS],
                    help="a preset -- pattern and four colours -- or a bare pattern name "
                         f"(default {looks.DEFAULT}); --colours overrides the colours")
    ap.add_argument("--colours", default=None, metavar="BODY,PATTERN,PRIMARY,SECONDARY",
                    help="hex colours written into the 3MF; fewer than four and the "
                         "rest come from the look")
    ap.add_argument("--format", default="both", choices=["3mf", "stl", "both"])
    ap.add_argument("--border", action="store_true", help="a border line round a card")
    ap.add_argument("--chamfer", type=float, default=cards.CHAMFER,
                    help=f"45-degree break on the outer edges, mm (default {cards.CHAMFER:g})")
    ap.add_argument("--logo", default=None, metavar="FILE.svg",
                    help="brokerage logo, raised on the front beside the name")
    ap.add_argument("--logo-height", type=float, default=None,
                    help="logo height in mm (default: 62%% of the face)")
    ap.add_argument("--design", default=None, metavar="FILE.svg",
                    help="an SVG that is the whole front -- replaces name, company, "
                         "phone and logo; the fields then only name the file")
    ap.add_argument("--link", default="", help="the URL the tag will carry")
    ap.add_argument("--qr", action="store_true",
                    help="also raise a QR code for --link on the back")
    ap.add_argument("--batch", default=None, metavar="FILE",
                    help="one person per line -- name, company, phone, link -- tab or "
                         "comma separated; writes every card onto one plate")
    ap.add_argument("--bed", type=float, default=220.0,
                    help="plate width the batch wraps at, mm (default 220)")
    ap.add_argument("--font", default=None, metavar="FACE",
                    help="for --kind name, one of "
                         + ", ".join(f"{k} ({v['font']})" for k, v in typefaces.FACES.items())
                         + f" (default {typefaces.DEFAULT}); or the path to a TTF of your "
                           "own, which is all a card or a fob will take -- their lettering "
                           "is small and wants a bold sans")
    ap.add_argument("--out", default=str(ROOT / "stl"), help="where to write the STLs")
    ap.add_argument("--preview", action="store_true", help="also render PNGs to previews/")
    args = ap.parse_args()

    if not args.batch and not any([args.name, args.company, args.phone, args.role,
                                   args.email, args.design]):
        ap.error("give at least one of --name / --company / --phone / --role / --email "
                 "/ --design, or --batch")
    if args.qr and not args.link and not args.batch:
        ap.error("--qr needs --link")

    tag = dict(thick=args.tag_thick)
    if args.tag:
        try:
            tag["w"], tag["h"] = (float(v) for v in args.tag.lower().split("x"))
        except ValueError:
            ap.error(f"--tag wants WxH in mm, e.g. 35x22 -- got {args.tag!r}")

    preset = looks.PRESETS.get(args.look)
    look = preset["pattern"] if preset else args.look
    layout = args.layout or (preset["layout"] if preset else "centred")
    colours = list(preset["colours"] if preset else cards.COLOURS)
    if args.colours:
        given = [c.strip() for c in args.colours.split(",")]
        if len(given) > 4 or not all(re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in given):
            ap.error(f"--colours wants up to four hex colours like #141414,#2e2e2e,"
                     f"#f2f2f2,#9a9a9a -- got {args.colours!r}")
        colours[:len(given)] = given
    colours = tuple(colours)
    # Flush is right for a card, whose colours are inlaid in the face; a name
    # keyring wants its letters standing on the outline.
    rise = args.rise if args.rise is not None else (
        nametag.RISE if args.kind == "name" else cards.RISE)

    if args.kind == "name":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        common = dict(font=args.font, cap=args.cap, rise=rise, ring_d=args.ring,
                      ring=args.ring > 0.5, outline=not args.flat)
        if args.batch:
            rows = cards.parse_batch(Path(args.batch).read_text())
            print(f"building {len(rows)} keyrings:")
            parts, infos = nametag.build_batch(rows, **common)
            for info in infos:
                report_name(info["label"], info)
            written = []
            if args.format != "stl":
                (out / "batch_keyrings.3mf").write_bytes(
                    cards.export_3mf(parts, colours, row_w=args.bed))
                written.append("batch_keyrings.3mf")
            if args.format != "3mf":
                cards.plate(parts, row_w=args.bed).export(out / "batch_keyrings.stl")
                written.append("batch_keyrings.stl")
            print(f"  -> {', '.join(written)}: {len(parts)} on a "
                  f"{cards.plate(parts, row_w=args.bed).extents[0]:.0f} mm plate")
            return
        if not args.name:
            ap.error("--kind name needs --name")
        parts, info = nametag.build(args.name, **common)
        stem = f"{slug(args.name)}_keyring"
        written = []
        if args.format != "3mf":
            parts[0]["mesh"].export(out / f"{stem}.stl")
            written.append(f"{stem}.stl")
        if args.format != "stl":
            (out / f"{stem}.3mf").write_bytes(cards.export_3mf(parts, colours))
            written.insert(0, f"{stem}.3mf")
        print("building:")
        report_name(", ".join(written), info)
        return


    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    kinds = ["card", "fob"] if args.kind == "both" else [args.kind]
    common = dict(font=args.font, tag=tag, tap_text=args.tap, tag_mode=args.tag_mode,
                  border=args.border, rise=rise, chamfer=args.chamfer,
                  logo=args.logo, logo_h=args.logo_height, qr=args.qr,
                  design=args.design, look=look, colours=colours, layout=layout,
                  placeholder=args.placeholder)

    if args.batch:
        rows = cards.parse_batch(Path(args.batch).read_text())
        print(f"building {len(rows)} people:")
        for kind in kinds:
            parts, infos = cards.build_batch(rows, kind, link=args.link, **common)
            for info in infos:
                report(info["label"], info)
            stem = f"batch_{kind}"
            written = []
            if args.format != "stl":
                (out / f"{stem}.3mf").write_bytes(
                    cards.export_3mf(parts, colours, row_w=args.bed))
                written.append(f"{stem}.3mf")
            if args.format != "3mf":
                cards.plate(parts, row_w=args.bed).export(out / f"{stem}.stl")
                written.append(f"{stem}.stl")
            plate = cards.plate(parts, row_w=args.bed).extents
            print(f"  -> {', '.join(written)}: {len(parts)} parts on a "
                  f"{plate[0]:.0f} x {plate[1]:.0f} mm plate")
        return

    print("building:")
    for kind in kinds:
        parts, info = cards.build(
            kind, args.name, args.company, args.phone, link=args.link,
            role=args.role, email=args.email, **common)
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
            bg = (30, 32, 36)
            flip = trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0])
            # the front face, and the back face, of the card glued up
            glued = [m for _, m in cards.assembly(parts)]
            mesh, cols = render.coloured(parts, colours, [flip @ m for m in glued])
            render.render(mesh, shots / f"{stem}_front.png", elev=58, azim=-90, zoom=1.04,
                          bg=bg, colours=cols)
            mesh, cols = render.coloured(parts, colours, glued)
            render.render(mesh, shots / f"{stem}_back.png", elev=58, azim=-90, zoom=1.04,
                          bg=bg, colours=cols)
            if len(parts) > 1:      # the halves pulled apart, and as they print
                lift = trimesh.transformations.translation_matrix((0, 0, 14.0))
                apart = [m if p["name"] != "back" else lift @ m for p, m in zip(parts, glued)]
                mesh, cols = render.coloured(parts, colours, apart)
                render.render(mesh, shots / f"{stem}_apart.png", elev=28, azim=-55, zoom=1.0,
                              bg=bg, colours=cols)
                plated = [trimesh.transformations.translation_matrix(s)
                          for _, s in cards.layout(parts)]
                mesh, cols = render.coloured(parts, colours, plated)
                render.render(mesh, shots / f"{stem}_plate.png", elev=50, azim=-90, zoom=1.0,
                              bg=bg, colours=cols)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        raise SystemExit(f"gen_cards.py: {exc}")
