"""The iPad case generator as a Vercel function, at /api/ipad.

The same handler as api/case.py -- src/case_app.py tells the two apart by the
path, and serves iPads from src/ipadcase.py when it has "ipad" in it. It is a
file of its own because Vercel's api/ directory is file-based, and the class
is written out here rather than imported under the name for the reason
api/case.py gives.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from case_app import Handler  # noqa: E402


class handler(Handler):
    """src/case_app.py's request handler, defined here so Vercel can see it."""
