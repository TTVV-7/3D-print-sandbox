"""Find and fetch Sketchfab models for the site, with their licences kept.

    python3 src/sketchfab.py search "dog collar"          # downloadable ones only
    python3 src/sketchfab.py info  <uid>                  # licence, author, size
    python3 src/sketchfab.py get   <uid> [--as dog]       # into public/assets/sketchfab/

The key is read from SKETCHFAB_TOKEN, in the environment or in a `.env` file at
the top of the repository -- which git ignores, so it never goes up with the
code.  Get one at sketchfab.com/settings/password (the "API token" box).
Searching needs no key; downloading does.

**The licence decides whether a model can go on a shop.**  Sketchfab models
come under Creative Commons licences or the store's own, and several of those
forbid commercial use outright: anything NonCommercial (BY-NC, BY-NC-SA,
BY-NC-ND) and the store's Editorial licence.  A site that sells tags is
commercial, so `get` refuses those unless told `--allow-noncommercial`, which is
for trying a model out and not for publishing it.  Everything else except CC0
wants the author credited where the model is shown, so every download is
recorded in public/assets/sketchfab/credits.json -- name, author, licence,
link -- and the page that shows it should show that line with it.

The model comes down as a GLB where Sketchfab offers one -- a single file a
browser can show with <model-viewer> -- and otherwise as the glTF archive,
unpacked into its own folder.  Either way, check the size before putting it on
a page: a 20 MB model is 20 MB every visitor downloads.

Standard library only: no requests, no dotenv.
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "assets" / "sketchfab"
CREDITS = OUT / "credits.json"
API = "https://api.sketchfab.com/v3"

# Anything this big wants a second thought before it goes on a page.
HEAVY_MB = 8.0


def token():
    """SKETCHFAB_TOKEN from the environment, else from ROOT/.env."""
    if os.environ.get("SKETCHFAB_TOKEN"):
        return os.environ["SKETCHFAB_TOKEN"].strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "SKETCHFAB_TOKEN":
                return value.strip().strip('"').strip("'")
    return None


def call(path, params=None, auth=False):
    url = path if path.startswith("http") else API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "3d-print-sandbox"})
    if auth:
        key = token()
        if not key:
            raise SystemExit("no SKETCHFAB_TOKEN -- put SKETCHFAB_TOKEN=... in .env at the "
                             "top of the repository")
        req.add_header("Authorization", f"Token {key}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SystemExit("Sketchfab refused the key (401) -- check SKETCHFAB_TOKEN")
        if e.code == 403:
            raise SystemExit("Sketchfab says this model cannot be downloaded (403)")
        if e.code == 429:
            raise SystemExit("too many requests (429) -- Sketchfab limits downloads per "
                             "day; try again later")
        raise


def licence(model):
    """(label, slug, commercial use allowed, credit required) for a model."""
    lic = model.get("license") or {}
    if isinstance(lic, str):
        lic = {"label": lic}
    label = lic.get("label") or lic.get("fullName") or "unknown licence"
    slug = (lic.get("slug") or "").lower()
    text = f"{slug} {label}".lower()
    commercial = not ("nc" in slug.split("-") or "noncommercial" in text.replace("-", "")
                      or "non-commercial" in text or slug == "ed" or "editorial" in text)
    if not slug and label == "unknown licence":
        commercial = False                   # unknown is not a yes
    credit = not (slug == "cc0" or "cc0" in text or "public domain" in text
                  or slug == "st" or "standard" in text)
    return label, slug, commercial, credit


def describe(model):
    label, _, commercial, credit = licence(model)
    user = model.get("user") or {}
    size = model.get("archives", {}).get("glb", {}).get("size") \
        or model.get("archives", {}).get("gltf", {}).get("size")
    return (f"{model.get('uid')}  {model.get('name')!r} by {user.get('username', '?')}\n"
            f"    {label} -- {'OK for the shop' if commercial else 'NOT for commercial use'}"
            f"{', credit the author' if commercial and credit else ''}"
            + (f", {size / 1e6:.1f} MB" if size else "")
            + f"\n    {link(model)}")


def link(model):
    """The model's page.  Search results come back with a viewerUrl whose
    slug is 'none', so those get the plain by-uid address instead."""
    url = model.get("viewerUrl") or ""
    return url if url and "/none-" not in url else f"https://sketchfab.com/models/{model.get('uid')}"


def search(query, count=12):
    data = call("/search", {"type": "models", "q": query, "downloadable": "true",
                            "count": count})
    for m in data.get("results", []):
        print(describe(m))


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "model"


def get(uid, name=None, allow_nc=False):
    model = call(f"/models/{uid}")
    label, slug, commercial, credit = licence(model)
    if not commercial and not allow_nc:
        raise SystemExit(f"{model.get('name')!r} is {label}: not for a site that sells "
                         "things.  --allow-noncommercial fetches it anyway, for trying out "
                         "only.")
    links = call(f"/models/{uid}/download", auth=True)
    name = slugify(name or model.get("name") or uid)
    OUT.mkdir(parents=True, exist_ok=True)

    if links.get("glb"):
        fmt, url, size = "glb", links["glb"]["url"], links["glb"].get("size")
    elif links.get("gltf"):
        fmt, url, size = "gltf", links["gltf"]["url"], links["gltf"].get("size")
    else:
        raise SystemExit(f"no glb or gltf download for {uid}: offered {sorted(links)}")
    if size and size / 1e6 > HEAVY_MB:
        print(f"note: {size / 1e6:.1f} MB -- heavy for a web page")

    # The download links are signed and short-lived, and carry no key.
    with urllib.request.urlopen(url, timeout=300) as r:
        blob = r.read()
    if fmt == "glb":
        path = OUT / f"{name}.glb"
        path.write_bytes(blob)
    else:
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for member in z.namelist():
                target = (folder / member).resolve()
                if not str(target).startswith(str(folder.resolve())):
                    raise SystemExit(f"refusing a path outside the folder: {member}")
            z.extractall(folder)
        path = folder / "scene.gltf"

    record(model, path, label, commercial, credit)
    print(f"saved {path.relative_to(ROOT)} ({len(blob) / 1e6:.1f} MB)")
    print(f"credit: {credit_line(model, label)}" if credit else "no credit needed")
    return path


def credit_line(model, label):
    user = model.get("user") or {}
    return (f"“{model.get('name')}” by {user.get('displayName') or user.get('username')} "
            f"on Sketchfab, {label}")


def record(model, path, label, commercial, credit):
    """Add the model to credits.json, replacing an earlier download of it."""
    user = model.get("user") or {}
    lic = model.get("license") or {}
    entry = dict(uid=model.get("uid"), name=model.get("name"),
                 file=str(path.relative_to(ROOT / "public")),
                 author=user.get("displayName") or user.get("username"),
                 author_url=user.get("profileUrl"),
                 model_url=link(model),
                 licence=label, licence_url=lic.get("url") if isinstance(lic, dict) else None,
                 commercial=commercial, credit_required=credit,
                 credit=credit_line(model, label) if credit else None)
    entries = json.loads(CREDITS.read_text()) if CREDITS.exists() else []
    entries = [e for e in entries if e.get("uid") != entry["uid"]] + [entry]
    CREDITS.write_text(json.dumps(entries, indent=2) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="downloadable models matching a query")
    s.add_argument("query")
    s.add_argument("--count", type=int, default=12)
    i = sub.add_parser("info", help="one model's licence, author and size")
    i.add_argument("uid")
    g = sub.add_parser("get", help="download a model into public/assets/sketchfab")
    g.add_argument("uid")
    g.add_argument("--as", dest="name", help="file name to save it under")
    g.add_argument("--allow-noncommercial", action="store_true",
                   help="fetch a NonCommercial or Editorial model anyway (not for the shop)")
    a = ap.parse_args()
    if a.cmd == "search":
        search(a.query, a.count)
    elif a.cmd == "info":
        print(describe(call(f"/models/{a.uid}")))
    else:
        get(a.uid, a.name, a.allow_noncommercial)
    sys.exit(0)
