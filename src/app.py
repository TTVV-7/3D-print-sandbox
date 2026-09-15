"""Browser front end for the card generator.

    python3 src/app.py            # then open http://127.0.0.1:8765

Fill in name, company and phone, watch the part turn in the viewer, download
it.  The 3MF carries each colour as a separate part, so the slicer opens it
set up for four filaments; the STL is one welded solid.  The preview is the
same solids, sent one after another with a colour and a place for each, so
the page can show the two halves of a split body glued up, pulled apart, or
lying on the plate as they print.

Standard library only -- no framework, nothing to install beyond what
src/cards.py already needs.  It listens on the loopback address; this is a tool
for the machine it runs on, not a service to put on a network.

The same Handler is also what api/model.py hands to Vercel, which runs
BaseHTTPRequestHandler subclasses as functions: one code path, local or hosted.
"""
import argparse
import gzip
import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import trimesh

import cards
import looks
import nametag

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "public" / "index.html"

# manifold is fast but there is no reason to have four keystrokes' worth of
# booleans running at once.  The last few builds are kept, so asking for the
# 3MF of what is on screen does not rebuild it.
BUILD = threading.Lock()
RECENT = {}
GEOMETRY = ("kind", "name", "company", "phone", "role", "email", "tap", "tag_w",
            "tag_h", "tag_thick", "tag_mode", "border", "rise", "font", "link", "qr",
            "logo", "batch", "design", "look", "layout", "placeholder",
            "cap", "ring_d", "outline")
HEX = re.compile(r"#[0-9a-fA-F]{6}$")


def palette(params):
    """The four colours from the form, defaults where a value is missing or
    not a hex colour."""
    given = params.get("colours") or []
    return tuple(c if isinstance(c, str) and HEX.match(c) else d
                 for c, d in zip(list(given) + [None] * 4, cards.COLOURS))


def preview(parts, info, row_w):
    """(bytes, description): every slot of every part, one after another in
    a binary STL, each in its own coordinates, plus where each goes -- its
    shift on the plate, and its transform into the assembled card -- so the
    page can draw either arrangement, colour every triangle by slot, and light
    up one field at a time.  A run is [colour slot, field, face, triangles].

    A split body also gets the NFC tag itself, as a slab in the joint.  It is
    not a printed part and has no place on the plate; it is there so that
    pulling the halves apart on screen shows what goes between them.
    """
    meshes, described = [], []
    assembled = dict((id(p), m) for p, m in cards.assembly(parts, row_w=row_w))
    for part, shift in cards.layout(parts, row_w=row_w):
        runs = []
        for g in part["groups"]:
            meshes.append(g["mesh"])
            runs.append([cards.SLOTS.index(g["slot"]), g["element"], g["face"],
                         int(len(g["mesh"].faces))])
        described.append(dict(name=part["name"], card=part.get("card", 0), slots=runs,
                              plate=[round(float(v), 4) for v in shift],
                              assembled=[round(float(v), 6)
                                         for v in assembled[id(part)].ravel()]))
        if part["name"] == "front" and info.get("joint"):
            slab = trimesh.creation.box(info["tag"])
            meshes.append(slab)
            place = assembled[id(part)] @ trimesh.transformations.translation_matrix(
                info["joint"])
            described.append(dict(name="tag", card=part.get("card", 0), tag=True,
                                  slots=[[len(cards.SLOTS), "tag", "joint",
                                      int(len(slab.faces))]],
                                  plate=None,
                                  assembled=[round(float(v), 6) for v in place.ravel()]))
    mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    return mesh.export(file_type="stl"), described


def model(params):
    """(bytes, info, content type) for one set of form values."""
    def num(key, default):
        try:
            return float(params.get(key) or default)
        except (TypeError, ValueError):
            return default

    colours = palette(params)
    keyed = {k: params.get(k) for k in GEOMETRY}
    if params.get("logo") or params.get("design"):
        keyed["colours"] = colours          # the fills sort into slots by colour
    key = json.dumps(keyed, sort_keys=True)
    with BUILD:
        if key not in RECENT:
            kind = params.get("kind", "fob")
            if kind == "name":
                # A name keyring has no faces, no tag and no layout: the word
                # is the whole object, so only these few settings reach it.
                keyring = dict(font=params.get("font") or None,
                               cap=num("cap", nametag.CAP),
                               rise=num("rise", nametag.RISE),
                               ring_d=num("ring_d", nametag.RING_D),
                               ring=num("ring_d", nametag.RING_D) > 0.5,
                               outline=bool(params.get("outline", True)),
                               colours=colours)
                if params.get("batch"):
                    rows = cards.parse_batch(params["batch"])
                    if not rows:
                        raise ValueError("the batch box is empty")
                    parts, infos = nametag.build_batch(rows, **keyring)
                    info = {**infos[0], "batch": len(rows), "label": "",
                            "w": max(i["w"] for i in infos),
                            "h": max(i["h"] for i in infos),
                            "volume": round(sum(i["volume"] for i in infos), 2),
                            "watertight": all(i["watertight"] for i in infos)}
                    RECENT[key] = parts, info
                else:
                    RECENT[key] = nametag.build(params.get("name", ""), **keyring)
                while len(RECENT) > 8:
                    del RECENT[next(iter(RECENT))]
                parts, info = RECENT[key]
                return _finish(params, parts, info, num)
            tag = dict(w=num("tag_w", cards.TAG["w"]), h=num("tag_h", cards.TAG["h"]),
                       thick=num("tag_thick", cards.TAG["thick"]))
            logo = params.get("logo") or None       # the SVGs' text, from the file pickers
            design = params.get("design") or None
            for what, svg in (("logo", logo), ("design", design)):
                if svg and not svg.lstrip().startswith("<"):
                    raise ValueError(f"the {what} has to be an SVG file")
            look = params.get("look") or "plain"
            if look not in looks.PATTERNS:
                raise ValueError(f"no such pattern: {look}")
            layout = params.get("layout") or "centred"
            if layout not in cards.LAYOUTS:
                raise ValueError(f"no such layout: {layout}")
            placeholder = params.get("placeholder") or None
            settings = dict(
                tag=tag, tap_text=params.get("tap", "TAP HERE"),
                tag_mode=params.get("tag_mode", "split"),
                border=bool(params.get("border", False)), rise=num("rise", cards.RISE),
                font=params.get("font") or None, logo=logo, design=design,
                qr=bool(params.get("qr")), link=params.get("link", ""),
                look=look, colours=colours, layout=layout, placeholder=placeholder,
                role=params.get("role", ""), email=params.get("email", ""))
            if params.get("batch"):
                rows = cards.parse_batch(params["batch"])
                if not rows:
                    raise ValueError("the batch box is empty")
                parts, infos = cards.build_batch(rows, kind, **settings)
                info = {**infos[0], "batch": len(rows), "label": "",
                        "nozzle": (None if any(i["nozzle"] is None for i in infos
                                               if i["logo"] or i["qr"])
                                   else min([i["nozzle"] for i in infos if i["nozzle"]],
                                            default=None)),
                        "volume": round(sum(i["volume"] for i in infos), 2),
                        "watertight": all(i["watertight"] for i in infos)}
                RECENT[key] = parts, info
            else:
                RECENT[key] = cards.build(
                    kind, name=params.get("name", ""), company=params.get("company", ""),
                    phone=params.get("phone", ""), **settings)
            while len(RECENT) > 8:
                del RECENT[next(iter(RECENT))]
        parts, info = RECENT[key]

    return _finish(params, parts, info, num)


def _finish(params, parts, info, num):
    """The same three answers whatever was built: a 3MF, an STL, or the
    preview the page draws."""
    # A batch, or a split body, is several parts; they go out as one plate --
    # one file to slice and one thing to show in the viewer.
    colours = palette(params)
    row_w = num("bed", 220.0) if params.get("batch") else None
    if params.get("format") == "3mf":
        return cards.export_3mf(parts, colours, row_w=row_w), info, "model/3mf"
    if params.get("format") == "stl":
        return cards.plate(parts, row_w=row_w).export(file_type="stl"), info, "model/stl"
    data, described = preview(parts, info, row_w)
    return data, {**info, "preview": described}, "model/stl"


def health():
    """GET /api/model: does the whole pipeline run where this is deployed?

    Builds the default fob and reports on it, so one request from a browser
    tells you the geometry libraries loaded, the font was found and a boolean
    came out watertight -- which is what a hosted function most often gets
    wrong, and what a 200 on the page alone would not show.
    """
    import time
    t = time.time()
    with BUILD:
        parts, info = cards.build("fob", "Self Test")
    return dict(ok=info["watertight"], font=cards.default_font(),
                built=f"{info['w']} x {info['h']} mm fob in {time.time() - t:.2f}s",
                python=__import__("sys").version.split()[0])


class Handler(BaseHTTPRequestHandler):
    server_version = "cards"

    def log_message(self, fmt, *a):          # one line per build, not per asset
        pass

    def _send(self, code, body, ctype, headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path in ("/api/model", "/model"):
            try:
                self._send(200, json.dumps(health()).encode(), "application/json")
            except Exception as exc:         # say what broke, rather than just 500
                self._send(500, json.dumps({"ok": False, "error": repr(exc)}).encode(),
                           "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path.split("?")[0] not in ("/api/model", "/model"):
            return self._send(404, b"not found", "text/plain")
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            params = json.loads(body or b"{}")
            data, info, ctype = model(params)
        except Exception as exc:             # a tag that will not fit, mostly
            payload = json.dumps({"error": str(exc)}).encode()
            return self._send(400, payload, "application/json")
        headers = [("X-Card-Info", json.dumps(info))]
        # An STL is a third repeated floats and squashes to about a third of its
        # size; the page asks for that when it can inflate it itself, and a
        # hosted function has a body-size ceiling that a batch plate would hit.
        if ctype == "model/stl" and params.get("gzip") and params.get("format") != "stl":
            data = gzip.compress(data, compresslevel=6)
            headers.append(("X-Compressed", "gzip"))
        print(f"  {info['kind']:5s} {info['w']:5.1f} x {info['h']:5.1f} mm  "
              f"{info['volume']:5.2f} cm^3  {ctype[6:]:3s} {len(data) / 1024:6.0f} kB")
        self._send(200, data, ctype, headers)


def serve(host="127.0.0.1", port=8765, open_browser=True):
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"card generator on {url}  (ctrl-c to stop)")
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
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    a = ap.parse_args()
    serve(a.host, a.port, not a.no_open)
