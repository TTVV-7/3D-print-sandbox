"""The phone case generator, from a terminal.

    python3 src/gen_case.py --phone iphone-17-pro --test-fit
    python3 src/gen_case.py --phone iphone-17-pro --art logo.svg --format all

The browser front end (`src/case_app.py`) and this are the same generator:
both hand a dictionary to `case_app.resolve`, which is the one place that
decides what a request means and clamps it to a range the geometry behaves in.
Nothing here reimplements any of that, so the page and the command line cannot
drift apart.

WHY THIS EXISTS. The page prints, under the preview, the command line that
reproduces the camera numbers it used -- ``--camera 67.9x34:12
--camera-margin 2.5,2`` -- so that a correction you make once outlives the
browser tab. It has been printing it at a command line that did not exist:
the full CLI lives in the upstream weave-trial repository and was never part
of this copy, so the one thing the flags were for, keeping a measurement,
could not be done. Now it can.

The other reason is that `--test-fit` is the whole safety net of this
generator -- print the walls and a rim, twenty minutes, find out whether the
numbers are right before committing six hours to them -- and a safety net you
have to open a browser and click through is one that gets skipped.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import case_app
from phonecase.profiles import CASES, FILAMENTS, PALETTES, PRINTERS
from phonecase.spec import PHONES

ROOT = Path(__file__).resolve().parent.parent

#: What each format is called on disk and which builder makes it.
FORMATS = {
    "gcode": ("gcode", case_app.gcode),
    "stl": ("stl", case_app.stl),
    "3mf": ("3mf", case_app.threemf),
}


def _camera(text: str) -> dict:
    """``WxH:R`` -- the same spelling the page prints back at you."""
    m = re.fullmatch(r'\s*([\d.]+)\s*[xX*]\s*([\d.]+)\s*(?::\s*([\d.]+))?\s*', text)
    if not m:
        raise argparse.ArgumentTypeError(
            f"--camera wants WxH or WxH:R (as in 39x39:11.5), not {text!r}")
    out = {"cameraW": float(m.group(1)), "cameraH": float(m.group(2))}
    if m.group(3):
        out["cameraR"] = float(m.group(3))
    return out


def _margin(text: str) -> dict:
    """``top,side``. A bar camera uses the side margin to set its width."""
    parts = [p for p in re.split(r'[,\s]+', text.strip()) if p]
    if not 1 <= len(parts) <= 2:
        raise argparse.ArgumentTypeError(
            f"--camera-margin wants top,side (as in 2.5,2), not {text!r}")
    out = {"cameraMarginTop": float(parts[0])}
    if len(parts) == 2:
        out["cameraMarginSide"] = float(parts[1])
    return out


def build(args) -> dict:
    """The request body, in the shape `case_app.resolve` reads."""
    params: dict = {
        "phone": args.phone,
        "fit": args.fit,
        "printer": args.printer,
        "filament": args.filament,
        "noButtons": args.no_buttons,
        "wrap": args.wrap,
        "brim": args.brim,
    }
    for key, value in (("clearance", args.clearance), ("wall", args.wall),
                       ("back", args.back), ("lip", args.lip),
                       ("lipInset", args.lip_inset),
                       ("layerHeight", args.layer),
                       ("firstLayer", args.first_layer),
                       ("artLayers", args.art_layers),
                       ("res", args.res), ("purge", args.purge),
                       ("artScale", args.art_scale),
                       ("artRotate", args.art_rotate)):
        if value is not None:
            params[key] = value
    for extra in (args.camera, args.camera_margin):
        if extra:
            params.update(extra)
    if args.test_fit is not None:
        params["testFit"] = True
        params["testFitRim"] = args.test_fit
    if args.palette:
        params["slots"] = [f"{s.hex}:{s.name}"
                           for s in PALETTES[args.palette].slots]
    if args.slots:
        params["slots"] = args.slots
    if args.art:
        params["art"] = Path(args.art).read_text()
    return params


def report(info: dict) -> int:
    """Print the printability report. Returns the number of problems."""
    size = info["size"]
    print(f"  {info['phone']}: {size[0]} x {size[1]} x {size[2]} mm, "
          f"wall {info['wall']} ({info['perimeters']} perimeters of "
          f"{info['wallLine']} mm), back {info['backThickness']} mm in "
          f"{info['solidLayers']} layers")
    cam = info["camera"]
    print(f"  camera: {cam['style']}, {cam['w']} x {cam['h']} mm, "
          f"r{cam['r']}, {cam['marginTop']} from the top and "
          f"{cam['marginSide']} from each side")
    print(f"  cutouts: {', '.join(info['cutouts'])}")
    if info.get("grams") is not None:
        print(f"  {info['grams']} g over {info['layers']} layers, "
              f"{info['toolChanges']} tool changes"
              + (f", {info['purgeGrams']} g purged"
                 if info.get("purgeGrams") else ""))
    if info.get("solid"):
        s = info["solid"]
        print(f"  solid: {s['triangles']} triangles, {s['volumeCm3']} cm3, "
              f"about {s['grams']} g"
              + (f", genus {s['holes']}" if "holes" in s else ""))
    for w in info["warnings"]:
        print(f"  warning: {w}")
    for p in info["problems"]:
        print(f"  PROBLEM: {p}")
    return len(info["problems"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phone", default="iphone-15-pro", choices=list(PHONES),
                    metavar="MODEL", help="which iPhone (default: %(default)s)")
    ap.add_argument("--fit", default="snug", choices=list(CASES),
                    help="a fit and a finish (default: %(default)s)")
    ap.add_argument("--camera", type=_camera, metavar="WxH:R",
                    help="camera opening, overriding the phone's estimate")
    ap.add_argument("--camera-margin", type=_margin, metavar="TOP,SIDE",
                    help="gap from the body edges to the camera opening; on a "
                         "bar camera the side margin sets the opening's width")
    ap.add_argument("--clearance", type=float, metavar="MM",
                    help="gap between phone and case, all the way round")
    ap.add_argument("--wall", type=float, metavar="MM")
    ap.add_argument("--back", type=float, metavar="MM",
                    help="back plate thickness")
    ap.add_argument("--lip", type=float, metavar="MM",
                    help="how far the wall rises past the screen")
    ap.add_argument("--lip-inset", type=float, metavar="MM",
                    help="how far the lip leans in over the screen")
    ap.add_argument("--no-buttons", action="store_true",
                    help="leave the side buttons covered")
    ap.add_argument("--test-fit", type=float, nargs="?", const=7.0,
                    metavar="RIM",
                    help="walls and a rim of back plate, middle left open: "
                         "half the filament, none of the purge, and every "
                         "dimension that can be wrong still in it. Print this "
                         "first. (default rim: 7 mm)")
    ap.add_argument("--layer", type=float, metavar="MM", help="layer height")
    ap.add_argument("--first-layer", type=float, metavar="MM")
    ap.add_argument("--art-layers", type=int, metavar="N",
                    help="how many bottom layers carry the artwork")
    ap.add_argument("--res", type=float, metavar="MM",
                    help="grid pitch of the section solver")
    ap.add_argument("--art", metavar="FILE.svg",
                    help="artwork for the back, painted by the AMS")
    ap.add_argument("--art-scale", type=float, metavar="X")
    ap.add_argument("--art-rotate", type=float, metavar="DEG")
    ap.add_argument("--wrap", action="store_true",
                    help="carry the artwork up the sides (costs a lot of purge)")
    ap.add_argument("--printer", default="generic-mmu", choices=list(PRINTERS))
    ap.add_argument("--filament", default="pla", choices=list(FILAMENTS))
    ap.add_argument("--palette", choices=list(PALETTES),
                    help="a named set of AMS slots")
    ap.add_argument("--slots", nargs="+", metavar="#RRGGBB:NAME",
                    help="the AMS slots, in order, overriding --palette")
    ap.add_argument("--purge", type=float, metavar="MM3",
                    help="volume flushed at each tool change")
    ap.add_argument("--brim", type=int, default=0, metavar="N")
    ap.add_argument("--format", default="stl", metavar="FMT",
                    choices=list(FORMATS) + ["all"],
                    help="gcode, stl, 3mf or all (default: %(default)s)")
    ap.add_argument("--out", default=str(ROOT / "stl"), metavar="DIR")
    ap.add_argument("--name", default=None, metavar="STEM",
                    help="base name for the files (default: the phone)")
    ap.add_argument("--check", action="store_true",
                    help="report only; write nothing")
    args = ap.parse_args(argv)

    params = build(args)
    stem = args.name or args.phone + ("-test-fit" if args.test_fit else "")
    out = Path(args.out)

    if args.check:
        _, info = case_app.preview(params)
        print(f"{stem}:")
        return 1 if report(info) else 0

    wanted = list(FORMATS) if args.format == "all" else [args.format]
    failed = 0
    for fmt in wanted:
        ext, builder = FORMATS[fmt]
        try:
            data, info, _ = builder(params)
        except ValueError as exc:
            # A test fit has no solid export, by design rather than by
            # oversight -- leaving the middle of the back plate unfilled is a
            # thing g-code can say and a mesh cannot.
            print(f"{stem}.{ext}: {exc}", file=sys.stderr)
            failed += 1
            continue
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{stem}.{ext}"
        path.write_bytes(data)
        print(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"
              f"  ({len(data) / 1024:.0f} kB)")
        if report(info):
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
