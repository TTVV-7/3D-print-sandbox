"""Browser front end for the generators.

    python3 src/app.py            # then open http://127.0.0.1:8765

Five shapes: the NFC logo card (src/logocard.py), a name keyring
(src/nametag.py), a pet collar tag (src/pettag.py), a sign enclosure
(src/signbox.py) and a stencil (src/stencil.py).  The NFC keyring fob
(src/cards.py) is archived: src/gen_cards.py still writes one, the app does
not.  Fill in the boxes, watch the part turn in the viewer,
download it.  The 3MF carries each colour as a separate part, so the slicer opens it
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

import numpy as np
import trimesh

import cards
import logocard
import nametag
import pettag
import signbox
import stencil
import typefaces

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "public" / "index.html"
# The spools on the shelf: what the colour pickers offer.  A static file, so
# Vercel serves it from public/ and this serves the same one locally.
SPOOLS = ROOT / "public" / "filaments.json"

# manifold is fast but there is no reason to have four keystrokes' worth of
# booleans running at once.  The last few builds are kept, so asking for the
# 3MF of what is on screen does not rebuild it.
BUILD = threading.Lock()
RECENT = {}
GEOMETRY = ("kind", "name", "company", "phone", "role", "email", "tap", "tag_w",
            "tag_h", "tag_thick", "tag_mode", "border", "rise", "font", "link", "qr",
            "logo", "batch", "design", "look", "layout", "placeholder",
            "cap", "ring_d", "outline",
            "plate_w", "plate_h", "margin", "bridge", "thick", "stencil_fit",
            "depth", "wall", "diffuse", "lid", "cable", "mount",
            "pet_shape", "pet_style", "pet_size", "pet_sides", "pet_note",
            "pet_link", "pet_border", "pet_collar", "pet_slot",
            "sign_shape", "cable_side", "pet_nfc", "pet_chip",
            "art", "card_size", "card_border", "card_backing", "card_holes",
            "card_colours", "card_bg", "card_ring", "card_at", "card_nfc",
            "card_chip", "card_back", "card_link", "card_both", "card_rises", "card_fit")

# The shapes the page can ask for.  "card" is the NFC business card, remade
# as src/logocard.py: the company's logo is the card's shape and colours.
# The two business-card-style parts before it -- the CR80 rectangle and the
# keyring fob with a name, company and phone on it -- are archived: their code
# is all still in src/cards.py and `src/gen_cards.py --kind card|fob` still
# writes either, but the app builds neither.
KINDS = ("card", "name", "pet", "stencil", "sign")
ARCHIVED = ("fob",)
# What a logo may be: SVG text, or an image as a browser's FileReader sends it.
IMAGE = re.compile(r"data:image/(png|jpeg|webp|gif|bmp|svg\+xml)[;,]")
HEX = re.compile(r"#[0-9a-fA-F]{6}$")


def face(params):
    """The face the form asked for, as a key from typefaces.FACES.

    Keys only, never a path: nametag.build() will happily open any TTF it is
    handed, and a path arriving in a request is a request to read a file off
    whatever machine is serving this.  The command line is where you point at
    a font of your own.
    """
    want = params.get("font") or typefaces.DEFAULT
    if want not in typefaces.FACES:
        raise ValueError(f"no such face: {want}")
    return want


def palette(params):
    """The four colours from the form, defaults where a value is missing or
    not a hex colour."""
    given = params.get("colours") or []
    return tuple(c if isinstance(c, str) and HEX.match(c) else d
                 for c, d in zip(list(given) + [None] * 4, cards.COLOURS))


MATERIAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 +._-]{0,23}$")


def filaments(params, colours):
    """One filament per colour slot -- its colour, material and spool name --
    from the page's spool pickers.  The colour is the palette's, so it is
    always a real hex; a material or a name that is not plain short text falls
    back rather than going into the 3MF's XML and config as given."""
    given = params.get("filaments") or []
    out = []
    for i, hexc in enumerate(colours):
        f = given[i] if i < len(given) and isinstance(given[i], dict) else {}
        material = f.get("material") if isinstance(f.get("material"), str) else ""
        name = f.get("name") if isinstance(f.get("name"), str) else ""
        out.append(dict(hex=hexc,
                        material=material if MATERIAL.match(material) else "PETG",
                        name=name if MATERIAL.match(name) else ""))
    return out


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
    if info.get("kind") == "card" and (info.get("nfc") or {}).get("pause_z"):
        return at_the_pause(parts[0], info)
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
            # the fob's tags are rectangles; a logo card's sticker is round
            slab = (trimesh.creation.cylinder(radius=info["tag"][0] / 2.0,
                                              height=info["tag"][2], sections=64)
                    if info.get("kind") == "card" else trimesh.creation.box(info["tag"]))
            meshes.append(slab)
            place = assembled[id(part)] @ trimesh.transformations.translation_matrix(
                info["joint"])
            described.append(dict(name="tag", card=part.get("card", 0), tag=True,
                                  slots=[[len(cards.SLOTS), "tag", "joint",
                                      int(len(slab.faces))]],
                                  plate=None,
                                  assembled=[round(float(v), 6) for v in place.ravel()]))
        if part.get("prop") is not None:
            # What a stencil sized to a mug or a cake is standing on, to scale:
            # the one thing on screen that says how big the part really is.
            meshes.append(part["prop"])
            described.append(dict(name="prop", card=part.get("card", 0), prop=True,
                                  slots=[[len(cards.SLOTS) + 1, "prop", "prop",
                                          int(len(part["prop"].faces))]],
                                  plate=None,
                                  assembled=[round(float(v), 6)
                                             for v in assembled[id(part)].ravel()]))
    mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    return mesh.export(file_type="stl"), described


def at_the_pause(part, info):
    """The preview of a logo card with its sticker sealed in: the one part,
    cut at the height the print pauses at, so the viewer's "apart" view can
    show it the way it is at the pause -- the bottom with its pocket open,
    the sticker going in, the rest of the card lifted off above.  Only the
    preview is cut; the files are the one part.  The cut pieces keep the
    card's own coordinates, so glued up and on the plate they are simply the
    card, sitting where it prints."""
    z = info["nfc"]["pause_z"]
    big = cards.rounded_rect(1e3, 1e3, 0.0)
    below = cards.prisms([big], -10.0, z + 10.0)[0]
    above = cards.prisms([big], z, 100.0)[0]
    (_, shift), = cards.layout([part])
    meshes, described = [], []
    pieces = {"front": [], "back": []}       # named as the viewer lifts them:
    for g in part["groups"]:                 # "back" is the one that comes off
        if g["face"] == "front":
            pieces["back"].append((g, g["mesh"]))
        elif g["face"] == "back":
            pieces["front"].append((g, g["mesh"]))
        else:
            pieces["front"].append((g, cards.boolean("intersection", [g["mesh"], below])))
            pieces["back"].append((g, cards.boolean("intersection", [g["mesh"], above])))
    ident = [round(float(v), 6) for v in np.eye(4).ravel()]
    plate = [round(float(v), 4) for v in shift]
    for name in ("front", "back"):
        runs = []
        for g, m in pieces[name]:
            if not len(m.faces):
                continue
            meshes.append(m)
            runs.append([cards.SLOTS.index(g["slot"]), g["element"], g["face"],
                         int(len(m.faces))])
        described.append(dict(name=name, card=0, slots=runs, plate=plate, assembled=ident))
        if name == "front":
            n = info["nfc"]
            disc = trimesh.creation.cylinder(radius=n["d"] / 2.0, height=n["t"], sections=64)
            meshes.append(disc)
            place = trimesh.transformations.translation_matrix(
                (n["centre"][0], n["centre"][1], n["z0"] + n["t"] / 2.0))
            described.append(dict(name="tag", card=0, tag=True,
                                  slots=[[len(cards.SLOTS), "tag", "joint",
                                          int(len(disc.faces))]],
                                  plate=None,
                                  assembled=[round(float(v), 6) for v in place.ravel()]))
    return trimesh.util.concatenate(meshes).export(file_type="stl"), described


def model(params):
    """(bytes, info, content type) for one set of form values."""
    def num(key, default):
        # Missing is missing; 0 is a number.  `margin`, `bridge`, `rise` and
        # `ring_d` all mean something at zero -- no frame, loose islands, flush
        # lettering, no ring tab -- and a falsy test would quietly replace
        # every one of them with the default.
        value = params.get(key)
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    colours = palette(params)
    keyed = {k: params.get(k) for k in GEOMETRY}
    if params.get("logo") or params.get("design"):
        keyed["colours"] = colours          # the fills sort into slots by colour
    if params.get("kind") == "card":
        keyed["body"] = colours[0]          # logo colours near it fold into the body
    key = json.dumps(keyed, sort_keys=True)
    with BUILD:
        if key not in RECENT:
            kind = params.get("kind", "card")
            if kind in ARCHIVED:
                raise ValueError("the keyring fob is archived -- the NFC logo card took its "
                                 "place, and src/gen_cards.py still writes a fob")
            if kind not in KINDS:
                raise ValueError(f"no such shape: {kind}")
            if kind == "card":
                # The logo card: the logo, as SVG text or an image data: URL,
                # is the card's outline and its colours.  One design, so no
                # batch -- a stack of the same card is one file printed again.
                art = params.get("art") or None
                if art and not (art.lstrip().startswith("<") or IMAGE.match(art)):
                    raise ValueError("the logo has to be an SVG, PNG, JPEG or WebP")
                RECENT[key] = logocard.build(
                    art, size=num("card_size", logocard.SIZE),
                    border=num("card_border", logocard.BORDER),
                    backing=params.get("card_backing") or "outline",
                    fill_holes=bool(params.get("card_holes", True)),
                    max_colours=int(num("card_colours", logocard.INLAYS)),
                    keep_background=bool(params.get("card_bg")),
                    ring=params.get("card_ring") or "tab",
                    ring_at=params.get("card_at") or "top-left",
                    ring_d=num("ring_d", logocard.RING_D),
                    rise=num("rise", 0.0), colours=colours,
                    nfc=bool(params.get("card_nfc", True)),
                    chip_d=num("card_chip", 0.0) or None,
                    back=params.get("card_back") or "arcs",
                    link=params.get("card_link", ""),
                    both=bool(params.get("card_both")),
                    fit=params.get("card_fit") or "halves",
                    # {slot: mm}, only when each colour has its own height
                    rises={k: float(v) for k, v in params["card_rises"].items()
                           if isinstance(v, (int, float, str)) and str(v).strip()}
                    if isinstance(params.get("card_rises"), dict) else None)
                while len(RECENT) > 8:
                    del RECENT[next(iter(RECENT))]
                parts, info = RECENT[key]
                return _finish(params, parts, info, num)
            if kind == "name":
                # A name keyring has no front and back, no tag and no
                # layout: the word is the whole object, so only these few
                # settings reach it -- and one of them is which face to set
                # it in, which is the only place a font choice matters.
                keyring = dict(font=face(params),
                               # no height of its own means the face's own:
                               # a slab or a script needs a taller letter
                               # than the sans before its counters survive.
                               cap=num("cap", 0.0) or None,
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
            if kind == "pet":
                # A pet tag: the name on the front, the way home on the back.
                # The phone, the note and the QR link are shared by a batch
                # unless a row carries its own.
                shape = params.get("pet_shape") or "bone"
                if shape not in pettag.SHAPES:
                    raise ValueError(f"no such tag shape: {shape}")
                tag = dict(phone=params.get("phone", ""),
                           note=params.get("pet_note", ""),
                           link=params.get("pet_link", ""),
                           shape=shape, style=params.get("pet_style") or "hanging",
                           size=num("pet_size", 0.0) or None,
                           sides=params.get("pet_sides") or "two",
                           font=face(params), rise=num("rise", 0.0),
                           border=bool(params.get("pet_border")),
                           ring_d=num("ring_d", pettag.RING_D),
                           collar=num("pet_collar", pettag.COLLAR),
                           slot=num("pet_slot", pettag.SLOT), colours=colours,
                           nfc=bool(params.get("pet_nfc")),
                           # 0 or missing: the biggest usual sticker that fits
                           chip_d=num("pet_chip", 0.0) or None)
                if params.get("batch"):
                    rows = pettag.parse_batch(params["batch"])
                    if not rows:
                        raise ValueError("the batch box is empty")
                    parts, infos = pettag.build_batch(rows, **tag)
                    info = {**infos[0], "batch": len(rows), "label": "",
                            "w": max(i["w"] for i in infos),
                            "h": max(i["h"] for i in infos),
                            "phone_cap": min((i["phone_cap"] for i in infos
                                              if i["phone_cap"]), default=None),
                            "volume": round(sum(i["volume"] for i in infos), 2),
                            "watertight": all(i["watertight"] for i in infos),
                            "thin": sorted({t for i in infos for t in i["thin"]})}
                    RECENT[key] = parts, info
                else:
                    RECENT[key] = pettag.build(params.get("name", ""), **tag)
                while len(RECENT) > 8:
                    del RECENT[next(iter(RECENT))]
                parts, info = RECENT[key]
                return _finish(params, parts, info, num)
            if kind == "stencil":
                # The artwork arrives in the same field a card's full-front
                # design does, and for the same reason: it is an SVG that is
                # the whole of the thing.
                art = params.get("design") or None
                if art and not art.lstrip().startswith("<"):
                    raise ValueError("the artwork has to be an SVG file")
                plate = dict(svg=art, font=face(params),
                             w=num("plate_w", stencil.W), h=num("plate_h", stencil.H),
                             thick=num("thick", stencil.THICK),
                             margin=num("margin", stencil.MARGIN),
                             bridge=num("bridge", stencil.BRIDGE),
                             # a disc sized to a mug or a cake, or the rectangle
                             fit=params.get("stencil_fit") or None,
                             colours=colours)
                if params.get("batch"):
                    rows = cards.parse_batch(params["batch"])
                    if not rows:
                        raise ValueError("the batch box is empty")
                    parts, infos = stencil.build_batch(rows, **plate)
                    info = {**infos[0], "batch": len(rows), "label": "",
                            "bridges": sum(i["bridges"] for i in infos),
                            "loose": sum(i["loose"] for i in infos),
                            "cut": min(i["cut"] for i in infos),
                            "web": min(i["web"] for i in infos),
                            "volume": round(sum(i["volume"] for i in infos), 2),
                            "watertight": all(i["watertight"] for i in infos),
                            "thin": sorted({t for i in infos for t in i["thin"]})}
                    RECENT[key] = parts, info
                else:
                    RECENT[key] = stencil.build(params.get("name", ""), **plate)
                while len(RECENT) > 8:
                    del RECENT[next(iter(RECENT))]
                parts, info = RECENT[key]
                return _finish(params, parts, info, num)
            if kind == "sign":
                # The artwork arrives in the same field the stencil's does, and
                # is lit the way the lettering is rather than cut away.
                art = params.get("design") or None
                if art and not art.lstrip().startswith("<"):
                    raise ValueError("the artwork has to be an SVG file")
                box = dict(svg=art, font=face(params),
                           w=num("plate_w", signbox.W), h=num("plate_h", signbox.H),
                           depth=num("depth", signbox.DEPTH),
                           wall=num("wall", signbox.WALL),
                           diffuse=num("diffuse", signbox.DIFFUSE),
                           margin=num("margin", signbox.MARGIN),
                           cable=num("cable", signbox.CABLE),
                           mount=params.get("mount") or "none",
                           # The box follows the letters unless asked for the
                           # rectangle, and the cable leaves by the back.
                           shape=params.get("sign_shape") or "letters",
                           cable_side=params.get("cable_side") or "right",
                           lid=bool(params.get("lid", True)),
                           colours=colours)
                if params.get("batch"):
                    rows = cards.parse_batch(params["batch"])
                    if not rows:
                        raise ValueError("the batch box is empty")
                    parts, infos = signbox.build_batch(rows, **box)
                    info = {**infos[0], "batch": len(rows), "label": "",
                            "w": max(i["w"] for i in infos),
                            "h": max(i["h"] for i in infos),
                            "stroke": min(i["stroke"] for i in infos),
                            "letters": sum(i["letters"] for i in infos),
                            "nozzle": (None if any(i["nozzle"] is None for i in infos)
                                       else min(i["nozzle"] for i in infos)),
                            "volume": round(sum(i["volume"] for i in infos), 2),
                            "watertight": all(i["watertight"] for i in infos),
                            "dim": any(i["dim"] for i in infos),
                            "thin": sorted({t for i in infos for t in i["thin"]})}
                    RECENT[key] = parts, info
                else:
                    RECENT[key] = signbox.build(params.get("name", ""), **box)
                while len(RECENT) > 8:
                    del RECENT[next(iter(RECENT))]
                parts, info = RECENT[key]
                return _finish(params, parts, info, num)
            raise ValueError(f"no builder for {kind}")          # every kind returns above
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
        if params.get("kind") in ("pet", "card"):
            # Each slot on its own filament, colours and materials named, so
            # a TPU tag with PETG lettering opens ready to slice as one print.
            # A sealed NFC chip needs the print to stop above its pocket;
            # every tag on a plate has its pocket at the same height.
            pauses = [(info["nfc"]["resume_z"], "Drop the NFC chip into the pocket")] \
                if info.get("nfc") and info["nfc"].get("resume_z") else []
            return (cards.export_3mf_tools(parts, filaments(params, colours), row_w=row_w,
                                           pauses=pauses),
                    info, "model/3mf")
        return cards.export_3mf(parts, colours, row_w=row_w), info, "model/3mf"
    if params.get("format") == "stl":
        if params.get("kind") == "card":
            parts = logocard.weld(parts)          # one solid a part, only for this
        return cards.plate(parts, row_w=row_w).export(file_type="stl"), info, "model/stl"
    if params.get("format") == "glb" and params.get("kind") == "pet":
        # The product shot: the first tag, hanging on a split ring.
        return pettag.product_glb(parts[:1], info, colours), info, "model/gltf-binary"
    data, described = preview(parts, info, row_w)
    return data, {**info, "preview": described}, "model/stl"


def health():
    """GET /api/model: does the whole pipeline run where this is deployed?

    Builds the default logo card and reports on it, so one request from a browser
    tells you the geometry libraries loaded, the font was found and a boolean
    came out watertight -- which is what a hosted function most often gets
    wrong, and what a 200 on the page alone would not show.
    """
    import time
    t = time.time()
    with BUILD:
        parts, info = logocard.build()
    return dict(ok=info["watertight"], font=cards.default_font(),
                built=f"{info['w']} x {info['h']} mm logo card in {time.time() - t:.2f}s",
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
        elif path == "/filaments.json":
            self._send(200, SPOOLS.read_bytes(), "application/json")
        elif path.startswith("/assets/"):
            # Static files under public/assets -- the tile icons.  Resolved and
            # checked, so a path with .. in it cannot walk out of the folder.
            base = (ROOT / "public" / "assets").resolve()
            f = (ROOT / "public" / path.lstrip("/")).resolve()
            kinds = {".webp": "image/webp", ".png": "image/png", ".glb": "model/gltf-binary",
                     ".json": "application/json"}
            if base in f.parents and f.is_file() and f.suffix in kinds:
                self._send(200, f.read_bytes(), kinds[f.suffix],
                           [("Cache-Control", "public, max-age=3600")])
            else:
                self._send(404, b"not found", "text/plain")
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
