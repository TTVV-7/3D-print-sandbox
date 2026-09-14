"""The card generator as a Vercel function.

Vercel looks for a Python entrypoint by name -- api/index.py is one of them --
and runs the BaseHTTPRequestHandler subclass it finds there called `handler`.
src/app.py already has one, so this file is the import.  The page itself is
public/index.html, which Vercel serves as a static file, and it calls
/api/model exactly as it does against the local server.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app import Handler as handler  # noqa: E402,F401
