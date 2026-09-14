"""The card generator as a Vercel function.

Vercel finds a Python entrypoint by name -- api/index.py is one -- and then
looks *inside the file* for the thing to run: an `app` or a `handler`.  That
look is static, so the class has to be defined here; importing src/app.py's
Handler under the name was not enough, and the file silently built as nothing.
The page itself is public/index.html, which Vercel serves as a static file,
and it calls /api/model exactly as it does against the local server.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app import Handler  # noqa: E402


class handler(Handler):
    """src/app.py's request handler, defined here so Vercel can see it."""
