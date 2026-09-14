"""The card generator as a Vercel function.

Vercel runs a BaseHTTPRequestHandler subclass named `handler` from any file
under api/; src/app.py already has one, so this file is the import.  The page
itself is public/index.html, which Vercel serves as a static file, and it
calls /api/model exactly as it does against the local server.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app import Handler as handler  # noqa: E402,F401
