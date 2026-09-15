"""The faces a name keyring can be set in.

A keyring is not a page.  The letters are the object, so a face has to hold up
as plastic and not only as a shape, and the three things that decide whether
it does are measured here rather than left to the caller:

  **weld** -- how far each glyph grows before the union (nametag.weld_together).
  A fat face is most of the way to one piece already and wants little of it; a
  light script wants the full 0.5 mm, which closes its gaps and fattens its
  thinnest strokes while it is there.

  **gap** -- how close the ink of one letter is walked to the ink of the last.
  Slightly negative suits a face whose letters are all different shapes, where
  overlapping them is free; a condensed face is mostly vertical stems, and an
  I welded to an E at -0.15 mm is one fat stem rather than two letters, so
  those want daylight between them and the weld to close it.

  **min_cap** -- the letter height under which that weld shuts the face's
  counters.  Growing a glyph outward shrinks its counter by about twice the
  weld, and anything left under a nozzle wide is filled in as unprintable, so
  a face whose `a` is a slot rather than a hole -- Alfa Slab One, Pacifico --
  needs a taller letter before the hole survives at all.  A word set under
  this height comes out as a row of blobs, which is why it is the height the
  keyring starts at rather than a note in the margin.

None of the three is a guess.  They come from setting "Mia", "Abbey", "Freddie",
"Oscar", "Noah", "Sophie", "Gigi" and "Benjamin" in each face at every weld
from 0.5 down to 0.3 mm and every height from 10 to 26 mm, and counting the
counters that closed: `min_cap` is the shortest letter at which none of them
did, at a weld of 0.35 mm or more -- below that the outline the weld leaves
round the letters is thinner than one extrusion line and stops printing as an
outline at all.  A name is welcome to go under it; the readout says what it
cost.

Everything here ships in src/fonts next to the code, for the same reason the
sans always did: a hosted function is guaranteed to carry its source and not
necessarily anything else, and Vercel has no system fonts at all.  Each face's
licence sits beside it -- five of the six are under the SIL Open Font Licence,
Chewy is Apache 2.0.
"""
from pathlib import Path

DIR = Path(__file__).resolve().parent / "fonts"

# The plain sans is the one face that might already be on the machine, so it
# keeps the old search: the bundled copy first, then the usual system paths,
# then whatever Arial the platform calls Arial.
SEARCH = [
    str(DIR / "LiberationSans-Bold.ttf"),
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

# key -> what the page shows, what it sets in, and what the keyring needs of it.
FACES = {
    "sans": dict(
        label="Sans",
        font="Liberation Sans Bold",
        note="Plain and heavy.  The one that fits any name and any length.",
        file=None,                  # the search above, so a system copy will do
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Steve Matteson / Ascender Corp."),
    "geometric": dict(
        label="Geometric",
        font="Poppins Bold",
        note="Circular bowls and a single-storey a -- the widest counters "
             "here, and the one that holds up smallest after the sans.",
        file="Poppins-Bold.ttf",
        weld=0.5, gap=-0.15, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, Indian Type Foundry, "
                "Jonny Pinhorn, Ninad Kale"),
    "rounded": dict(
        label="Rounded",
        font="Chewy",
        note="Soft and bouncy, drawn with a fat marker.  Latin-1 only, so no "
             "Polish or Turkish accents.",
        file="Chewy-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=16.0,
        licence="Apache Licence 2.0, Sideshow (Font Diner)"),
    "script": dict(
        label="Script",
        font="Pacifico",
        note="A brush script.  The letters run into each other before the "
             "weld is asked to do anything, which is what a name keyring "
             "usually wants -- but its lower case is small for its capitals, "
             "so it is the face that needs the most height.",
        file="Pacifico-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=20.0,
        licence="SIL Open Font Licence 1.1, Vernon Adams, Jacques Le Bailly, "
                "Botjo Nikoltchev, Ani Petrova"),
    "slab": dict(
        label="Slab",
        font="Alfa Slab One",
        note="Fat slab serifs, heavy enough that the weld is barely needed.  "
             "Its counters are slots rather than holes, so it wants a tall "
             "letter to keep them open.",
        file="AlfaSlabOne-Regular.ttf",
        # slab serifs reach for each other: left overlapping, one letter's
        # bracket swallows the next one's
        weld=0.35, gap=0.25, min_cap=18.0,
        licence="SIL Open Font Licence 1.1, JM Sole"),
    "condensed": dict(
        label="Condensed",
        font="Bebas Neue",
        note="Tall narrow capitals -- lower case comes out as capitals too.  "
             "The one for a long name, at about two thirds the width.",
        file="BebasNeue-Regular.ttf",
        # all stems: without a gap the I in FREDDIE welds into the E beside it
        weld=0.4, gap=0.3, min_cap=16.0,
        licence="SIL Open Font Licence 1.1, Ryoichi Tsunekawa"),
}

DEFAULT = "sans"


def default_font():
    """The first font in SEARCH that exists.

    A miss is an ordinary error, not a SystemExit: raised inside a request
    handler, SystemExit takes the whole process down with no traceback, which
    is exactly how the hosted version first failed.
    """
    for path in SEARCH:
        if Path(path).exists():
            return path
    raise FileNotFoundError("no font found; looked in " + ", ".join(SEARCH)
                            + " -- pass --font /path/to/Font.ttf")


def face(value=None):
    """The face `value` names, as a dict with a `path` on it.

    `value` is a key from FACES, or a path to a TTF of your own -- the command
    line takes either, the browser only the keys, since a path in a request is
    a request to read a file off the server.  An outside font has no measured
    weld or minimum height, so those come back None and nametag falls back to
    its own constants.
    """
    key = value or DEFAULT
    if key in FACES:
        spec = FACES[key]
        path = str(DIR / spec["file"]) if spec["file"] else default_font()
        if not Path(path).exists():
            raise FileNotFoundError(f"{spec['font']} is missing from {DIR}")
        return dict(spec, key=key, path=path)
    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(
            f"no such face or font file: {value!r} -- the faces are "
            + ", ".join(FACES) + ", or give the path to a TTF")
    return dict(key=None, label=path.stem, font=path.stem, note="", file=path.name,
                path=str(path), weld=None, gap=None, min_cap=None, licence="")

