"""Browser front end for the phone case generator.

    python3 src/case_app.py        # then open http://127.0.0.1:8766

Pick a phone, drop in an SVG, watch the back of the case redraw, download the
g-code. Same shape as src/app.py -- one BaseHTTPRequestHandler that serves the
page locally and is handed to Vercel by api/case.py -- so there is one code
path whether it is running on your laptop or hosted.

The generator itself is src/phonecase/, vendored from the Weave-Trial repo,
which is where it is developed and tested. See PROVENANCE below.

Two things this file exists to do that the library does not:

**Keep a web request from becoming a compute bill.** Every number off the
form is clamped to a range the generator is known to behave in, the phone and
the preset have to be names that already exist, and the section grid has a
floor. Nothing a request says can make a loop run longer than the caller is
willing to wait.

**Answer in two speeds.** Drawing the page needs the artwork layers and
nothing else -- what the back of a case looks like is decided there -- so a
preview builds two layers in about a second. Only pressing Download builds
the whole case, which is five to fifteen seconds of real work.
"""
import argparse
import gzip
import json
import sys
import threading
import webbrowser
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phonecase.gcode import plan_tower, tower_stats, write as write_gcode
from phonecase.paint import Palette, plan as plan_paint
from phonecase.preview import render
from phonecase.profiles import CASES, FILAMENTS, PALETTES, PRINTERS
from phonecase.spec import PHONES, CaseSpec, check_case
from phonecase.solid import (MeshUnavailable, build_solid, mesh_to_stl,
                             stats as solid_stats)
from phonecase.svgart import load as load_svg
from phonecase.threemf import (colour_parts, parts_to_3mf,
                               stats as threemf_stats)
from phonecase.toolpath import build, stats

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "public" / "case.html"

#: The commit of ttvv-7/weave-trial that src/phonecase was taken from.
#: Update it with the copy, so a bug here can be traced to a source there.
#:
#: phonecase/preview.py has since been edited here rather than there, twice,
#: and the two want different things done about them:
#:
#: * the dark-mode colours for the sheet, which are about this page showing
#:   the picture rather than about the generator drawing it;
#: * the lens layout for a plateau camera, which is a plain bug -- all three
#:   lenses were drawn overlapping, and the bar had a flash on it and
#:   nothing else. That one belongs upstream.
#:
#: The file no longer matches this commit, and the next copy across will
#: overwrite both. Port the lens fix to weave-trial; port or re-apply the
#: <style> block.
PROVENANCE = "f7bf3c7"

#: Requests bigger than this are not artwork. The SVG reader has its own,
#: lower, limit; this one is about not buffering a payload to find out.
MAX_BODY = 6 << 20

#: Finer than this is invisible under a 0.42 mm line and costs seconds.
MIN_RES = 0.3


def _num(params, key, default, lo, hi):
    """A number off the form, clamped. Anything unparseable is the default."""
    try:
        v = float(params.get(key, default))
    except (TypeError, ValueError):
        return default
    if v != v:                                   # NaN compares false to both
        return default
    return max(lo, min(hi, v))


def _flag(params, key, default=False):
    v = params.get(key, default)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")


def _one_of(params, key, table, default):
    want = params.get(key) or default
    if want not in table:
        raise ValueError(f"no such {key}: {want!r}")
    return want


def palette_from(params):
    """The AMS slots off the form.

    Slot colours arrive as plain ``#rrggbb`` strings; anything else is a
    request to put arbitrary text into the g-code comments, so the palette
    parser is the only thing that gets to decide what a colour is.
    """
    given = params.get("slots")
    if not given:
        return PALETTES["duo"]
    if not isinstance(given, list) or len(given) > 8:
        raise ValueError("slots must be a list of at most 8 colours")
    entries = []
    for i, slot in enumerate(given[:8]):
        if isinstance(slot, dict):
            colour = str(slot.get("hex", ""))[:9]
            name = str(slot.get("name", ""))[:24]
        else:
            colour, _, name = str(slot)[:40].partition(":")
        name = "".join(c for c in name if c.isalnum() or c in " -_") or f"slot {i}"
        entries.append(f"{i}={colour.strip()}:{name.strip()}")
    return Palette.parse(entries)


def resolve(params):
    """Everything the generator needs, from a request body it does not trust."""
    phone = PHONES[_one_of(params, "phone", PHONES, "iphone-15-pro")]

    # The camera opening is the least certain number in the whole generator
    # -- body sizes are published, this one is not -- so it is the one the
    # form gets to correct. Clamped to what could plausibly be a camera on a
    # phone this size, not to what happens to be in the table.
    cam = {}
    for key, attr, lo, hi in (
            ("cameraW", "camera_w", 4.0, phone.width),
            ("cameraH", "camera_h", 4.0, phone.length / 2),
            ("cameraR", "camera_r", 0.0, 30.0),
            ("cameraMarginTop", "camera_margin_top", 0.0, 40.0),
            ("cameraMarginSide", "camera_margin_side", 0.0, 40.0)):
        if params.get(key) is not None:
            cam[attr] = _num(params, key, getattr(phone, attr), lo, hi)
    if cam:
        cam["camera_r"] = min(cam.get("camera_r", phone.camera_r),
                              cam.get("camera_w", phone.camera_w) / 2,
                              cam.get("camera_h", phone.camera_h) / 2)
        phone = replace(phone, **cam)
    preset = dict(CASES[_one_of(params, "fit", CASES, "snug")])

    for key, attr, lo, hi in (("clearance", "clearance", 0.1, 1.0),
                              ("wall", "wall", 0.8, 4.0),
                              ("back", "back_thickness", 0.6, 4.0),
                              ("lip", "lip", 0.0, 4.0),
                              ("lipInset", "lip_inset", 0.0, 2.5)):
        if params.get(key) is not None:
            preset[attr] = _num(params, key, preset.get(attr, 1.0), lo, hi)
    preset["layer_height"] = _num(params, "layerHeight", 0.2, 0.1, 0.32)
    preset["art_layers"] = int(_num(params, "artLayers", 2, 1, 6))
    preset["section_res"] = _num(params, "res", 0.45, MIN_RES, 1.2)

    spec = CaseSpec(phone, **preset)
    spec.cutouts = phone.cutouts(back_thickness=spec.back_thickness,
                                 cavity_depth=spec.cavity_depth,
                                 clearance=spec.clearance,
                                 buttons=not _flag(params, "noButtons"))

    printer = PRINTERS[_one_of(params, "printer", PRINTERS, "generic-mmu")]
    filament = FILAMENTS[_one_of(params, "filament", FILAMENTS, "pla")]
    if params.get("purge") is not None:
        filament = replace(filament,
                           purge_mm3=_num(params, "purge", 110, 0, 600))

    art = None
    raw = params.get("art")
    if raw:
        if not isinstance(raw, str):
            raise ValueError("art must be the text of an SVG file")
        art = load_svg(raw)                      # limit=True: this is a upload

    palette = palette_from(params)
    # The switch and the width are separate keys: the form sends a boolean
    # for the switch, and float(True) is 1.0, which would quietly become the
    # narrowest rim the clamp allows rather than the default.
    test_fit = _num(params, "testFitRim", 7.0, 3.0, 30.0) \
        if _flag(params, "testFit") else None
    if test_fit:
        art = None                               # a test fit is about fit

    place = dict(
        fit=_one_of(params, "artFit", ("contain", "cover", "stretch", "none"),
                    "contain"),
        box=_one_of(params, "artBox", ("content", "view"), "content"),
        margin=_num(params, "artMargin", 2.0, -10.0, 30.0),
        scale=_num(params, "artScale", 1.0, 0.05, 8.0),
        rotate=_num(params, "artRotate", 0.0, -360.0, 360.0),
        offset=(_num(params, "artX", 0.0, -120.0, 120.0),
                _num(params, "artY", 0.0, -200.0, 200.0)),
        mirror=not _flag(params, "noMirror"),
    )
    paint = plan_paint(art, palette, spec.outer_w, spec.outer_l, **place)

    # The body colour is whatever the artwork mostly is, unless asked.
    if art is not None and params.get("base") is None:
        area = paint.raster.area_mm2()
        dominant = max(area, key=area.get)
        if dominant != palette.base:
            palette = Palette(list(palette.slots), dominant)
            paint = plan_paint(art, palette, spec.outer_w, spec.outer_l, **place)
    elif params.get("base") is not None:
        base = int(_num(params, "base", 0, 0, len(palette) - 1))
        palette = Palette(list(palette.slots), base)
        paint = plan_paint(art, palette, spec.outer_w, spec.outer_l, **place)

    return dict(spec=spec, paint=paint, palette=palette, printer=printer,
                filament=filament, test_fit=test_fit,
                wrap=_flag(params, "wrap"),
                brim=int(_num(params, "brim", 0, 0, 10)),
                art=art)


def _camera_report(spec):
    """The camera numbers, and the command line that would reproduce them.

    Printed back because they are estimates: seeing what the generator
    actually used is how you find out it does not match the phone in your
    hand, and the flags are so a correction can outlive the browser tab.
    """
    p = spec.phone
    cam = next((c for c in spec.cutouts if c.name == "camera"), None)
    return {
        "style": p.camera_style,
        "lenses": p.lenses,
        "w": round(p.camera_w, 2), "h": round(p.camera_h, 2),
        "r": round(p.camera_r, 2),
        "marginTop": round(p.camera_margin_top, 2),
        "marginSide": round(p.camera_margin_side, 2),
        "centre": [round(cam.u, 2), round(cam.v, 2)] if cam else None,
        "flags": (f"--camera {p.camera_w:g}x{p.camera_h:g}:{p.camera_r:g} "
                  f"--camera-margin {p.camera_margin_top:g},"
                  f"{p.camera_margin_side:g}"),
    }


def report(r, path, st, tower_cost):
    """The numbers the page prints under the preview."""
    spec, palette = r["spec"], r["palette"]
    check = check_case(spec,
                       bed=(r["printer"].bed_x, r["printer"].bed_y,
                            r["printer"].max_z),
                       slots=r["printer"].tools,
                       used_slots=len(r["paint"].raster.used_slots()))
    return {
        "ok": check.ok,
        "problems": check.problems,
        "warnings": list(r["paint"].warnings) + check.warnings,
        "phone": spec.phone.name,
        "size": [round(spec.outer_w, 1), round(spec.outer_l, 1),
                 round(spec.height, 1)],
        "clearance": spec.clearance,
        "wall": spec.wall,
        "perimeters": spec.perimeters,
        "wallLine": round(spec.wall_line, 3),
        "backThickness": spec.back_thickness,
        "solidLayers": spec.solid_layers,
        "artLayers": spec.art_layers,
        "lip": spec.lip,
        "lipInset": spec.lip_inset,
        "lipOverhang": round(spec.lip_overhang_deg),
        "cutouts": [c.name for c in spec.cutouts],
        "camera": _camera_report(spec),
        "bodySlot": palette.base,
        "slots": [{"index": s.index, "name": s.name, "hex": s.hex}
                  for s in palette.slots],
        "colours": [{"rgb": "#%02x%02x%02x" % rgb, "slot": slot,
                     "share": round(share, 4)}
                    for rgb, slot, share in r["paint"].mapping],
        "areaBySlot": {str(k): round(v) for k, v in
                       r["paint"].raster.area_mm2().items()},
        "layers": st["layers"] if st else None,
        "grams": round(st["grams"], 1) if st else None,
        "gramsBySlot": {str(k): round(v, 2)
                        for k, v in st["per_slot_g"].items()} if st else None,
        "toolChanges": st["tool_changes"] if st else None,
        "pathLength": round(st["path_length_m"]) if st else None,
        "purgeGrams": round(tower_cost["grams"], 1) if tower_cost else None,
        "testFit": r["test_fit"],
    }


def preview(params):
    """(svg, report): what the back will look like, in about a second.

    Only the artwork layers are built. They are the ones that decide what the
    finished back looks like, and the other fifty are five to fifteen seconds
    the page would spend on something nobody can see.
    """
    r = resolve(params)
    path = build(r["spec"], r["paint"], wrap=r["wrap"], skirt=0,
                 test_fit=r["test_fit"],
                 max_layers=r["spec"].art_layers)
    svg = render(r["spec"], path, r["paint"])
    return svg, report(r, path, None, None)


def gcode(params):
    """(bytes, report, content type): the whole case, which is the slow one."""
    r = resolve(params)
    path = build(r["spec"], r["paint"], wrap=r["wrap"], brim=r["brim"],
                 test_fit=r["test_fit"])
    st = stats(r["spec"], path, density=r["filament"].density,
               filament_d=r["printer"].filament_diameter)
    tower = plan_tower(r["spec"], path, r["filament"])
    cost = tower_stats(r["spec"], path, tower, r["printer"], r["filament"])
    text = write_gcode(r["spec"], path, r["printer"], r["filament"],
                       r["paint"], tower=tower)
    return text.encode(), report(r, path, st, cost), "text/plain; charset=utf-8"


def stl(params):
    """(bytes, report, content type): the case as a solid.

    Geometry only -- an STL has no idea which filament lays down which line,
    so the artwork is not in it. It is here for slicing the case yourself, or
    painting it in your slicer's own colour tool.
    """
    r = resolve(params)
    try:
        solid = build_solid(r["spec"], test_fit=bool(r["test_fit"]))
    except MeshUnavailable as exc:              # not installed on this host
        raise ValueError(str(exc)) from None
    data = mesh_to_stl(solid, header=f"{params.get('phone', 'case')} - phonecase")
    info = report(r, None, None, None)
    ss = solid_stats(solid)
    info["solid"] = {
        "triangles": ss["triangles"],
        "volumeCm3": round(ss["volume_mm3"] / 1000.0, 2),
        "grams": round(ss["volume_mm3"] * r["filament"].density / 1000.0, 1),
        "holes": ss["genus"],
    }
    return data, info, "model/stl"


def threemf(params):
    """(bytes, report, content type): the case as a 3MF, colours and all.

    The one export that keeps the artwork: the back plate is cut into inlays,
    one solid per filament, so a slicer opens a single object with a part per
    colour instead of a shape it has to be told about.
    """
    r = resolve(params)
    if r["test_fit"]:
        raise ValueError(
            "a test fit leaves the middle of the back plate unfilled, which "
            "is a thing g-code can say and a solid cannot. Take the test fit "
            "as g-code")
    try:
        parts = colour_parts(r["spec"], r["paint"], wrap=r["wrap"])
    except MeshUnavailable as exc:
        raise ValueError(str(exc)) from None
    spec = r["spec"]
    data = parts_to_3mf(parts, origin=(spec.outer_w / 2, spec.outer_l / 2),
                        name=params.get("phone", "case"))
    info = report(r, None, None, None)
    ms = threemf_stats(parts)
    info["solid"] = {
        "triangles": ms["triangles"],
        "volumeCm3": round(ms["volume_mm3"] / 1000.0, 2),
        "grams": round(ms["volume_mm3"] * r["filament"].density / 1000.0, 1),
        "parts": ms["parts"],
        "perPart": ms["per_part"],
    }
    return data, info, "model/3mf"


def catalogue():
    """Everything the form's menus are made of, from the generator itself.

    The page does not carry its own copy of the phone list. Adding a phone to
    src/phonecase/spec.py puts it in the menu.
    """
    return {
        "ok": True,
        "provenance": PROVENANCE,
        # Each phone ships its camera defaults so the form can start from
        # them and put them back when you change phone.
        "phones": [{"id": k, "name": v.name,
                    "size": [v.length, v.width, v.thickness],
                    "camera": {"style": v.camera_style, "lenses": v.lenses,
                               "w": v.camera_w, "h": v.camera_h,
                               "r": v.camera_r,
                               "marginTop": v.camera_margin_top,
                               "marginSide": v.camera_margin_side}}
                   for k, v in PHONES.items()],
        "cases": [{"id": k, **v} for k, v in CASES.items()],
        "printers": [{"id": k, "name": v.name, "tools": v.tools,
                      "bed": [v.bed_x, v.bed_y]} for k, v in PRINTERS.items()],
        "filaments": [{"id": k, "purge": v.purge_mm3, "nozzle": v.nozzle_temp}
                      for k, v in FILAMENTS.items()],
        "palettes": {k: [{"index": s.index, "name": s.name, "hex": s.hex}
                         for s in v.slots] for k, v in PALETTES.items()},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "phonecase"

    def log_message(self, fmt, *a):              # one line per build
        pass

    def _send(self, code, body, ctype, headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/case", "/case.html"):
            return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        if path in ("/api/case", "/case.json"):
            try:
                return self._json(200, catalogue())
            except Exception as exc:             # say what broke, not just 500
                return self._json(500, {"ok": False, "error": repr(exc)})
        if path == "/example-art.svg":
            f = ROOT / "public" / "example-art.svg"
            return self._send(200, f.read_bytes(), "image/svg+xml")
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path.split("?")[0] not in ("/api/case", "/case.json"):
            return self._send(404, b"not found", "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(413, {"error": f"request is {length / 1e6:.1f} MB; "
                                             f"the limit is {MAX_BODY / 1e6:.0f} MB"})
        body = self.rfile.read(length)
        try:
            params = json.loads(body or b"{}")
            if not isinstance(params, dict):
                raise ValueError("expected a JSON object")
            want = params.get("want")
            want_file = want in ("gcode", "stl", "3mf")
            if want == "gcode":
                data, info, ctype = gcode(params)
            elif want == "stl":
                data, info, ctype = stl(params)
            elif want == "3mf":
                data, info, ctype = threemf(params)
            else:
                svg, info = preview(params)
                data, ctype = json.dumps({"svg": svg, "report": info}).encode(), \
                    "application/json"
        except ValueError as exc:                # a bad SVG or a bad number
            return self._json(400, {"error": str(exc)})
        except Exception as exc:
            return self._json(500, {"error": repr(exc)})

        headers = [("X-Case-Info", json.dumps(info))]
        # G-code is repetitive text and squashes to about a seventh of its
        # size; a hosted function has a response ceiling a whole case would
        # otherwise crowd. A binary STL is mostly floats and squashes less,
        # but it is a tenth of the size to begin with.
        if want_file and params.get("gzip"):
            data = gzip.compress(data, compresslevel=6)
            headers.append(("X-Compressed", "gzip"))
            headers.append(("Content-Encoding", "identity"))
        self._send(200, data, ctype, headers)


def serve(host="127.0.0.1", port=8766, open_browser=True):
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"phone case generator on {url}  (ctrl-c to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    a = ap.parse_args()
    serve(a.host, a.port, not a.no_open)
