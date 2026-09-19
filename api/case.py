"""The phone case generator as a Vercel function, at /api/case.

Vercel's api/ directory is file-based: this file answers /api/case, which is
the path public/case.html calls whether it is talking to Vercel or to
src/case_app.py. It runs the BaseHTTPRequestHandler subclass it finds
*defined* here under the name `handler` -- that look is static, so importing
src/case_app.py's Handler under the name is not enough and the class has to be
written out, the same as api/model.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from case_app import Handler  # noqa: E402


class handler(Handler):
    """src/case_app.py's request handler, defined here so Vercel can see it."""
