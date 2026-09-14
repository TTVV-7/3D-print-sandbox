"""Browser front end for the card generator.

    python3 src/app.py            # then open http://127.0.0.1:8765

Fill in name, company and phone, watch the part turn in the viewer, download
the STL.  The preview colours the raised lettering and the contactless mark
differently from the body, which is what you actually get out of the printer
if you put a filament change in at the two heights it reports.

Standard library only -- no framework, nothing to install beyond what
src/cards.py already needs.  It listens on the loopback address; this is a tool
for the machine it runs on, not a service to put on a network.
"""
import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cards

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "web" / "index.html"

# manifold is fast but there is no reason to have four keystrokes' worth of
# booleans running at once.
BUILD = threading.Lock()


def model(params):
    """(stl bytes, info) for one set of form values."""
    def num(key, default):
        try:
            return float(params.get(key) or default)
        except (TypeError, ValueError):
            return default

    tag = dict(w=num("tag_w", cards.TAG["w"]), h=num("tag_h", cards.TAG["h"]),
               thick=num("tag_thick", cards.TAG["thick"]))
    with BUILD:
        parts, info = cards.build(
            params.get("kind", "card"),
            name=params.get("name", ""), company=params.get("company", ""),
            phone=params.get("phone", ""), tag=tag,
            tap_text=params.get("tap", "TAP HERE"),
            tag_mode=params.get("tag_mode", "pocket"),
            border=bool(params.get("border", True)),
            font=params.get("font") or None)
    # A split body comes back as two parts; they go out as one plate, which is
    # one file to slice and one thing to show in the viewer.
    return cards.plate(parts).export(file_type="stl"), info


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
        if self.path.split("?")[0] in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/model":
            return self._send(404, b"not found", "text/plain")
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            params = json.loads(body or b"{}")
            stl, info = model(params)
        except Exception as exc:             # a tag that will not fit, mostly
            payload = json.dumps({"error": str(exc)}).encode()
            return self._send(400, payload, "application/json")
        print(f"  {info['kind']:5s} {info['w']:5.1f} x {info['h']:5.1f} mm  "
              f"{info['volume']:5.2f} cm^3  {len(stl) / 1024:6.0f} kB")
        self._send(200, stl, "model/stl",
                   [("X-Card-Info", json.dumps(info))])


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
