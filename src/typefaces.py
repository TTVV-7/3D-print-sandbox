"""The faces a name keyring or a stencil can be set in.

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
did, at the face's own weld -- never under 0.35 mm, because below that the
outline the weld leaves round the letters is thinner than one extrusion line
and stops printing as an outline at all.  `gap` comes out of the same setting:
it is the tightest spacing at which no letter's ink is still inside the last
one's over a run worth calling a merge, which is what turns the I of FREDDIE
and the E beside it into one fat stem.  A name is welcome to go under `min_cap`;
the readout says what it cost.

  **kinds** -- what the face is offered for, because the other thing set in
  these is a stencil, and a stencil wants the opposite of a keyring.  A keyring
  has to weld a word into one piece; a stencil has to keep a plate in one piece
  while cutting that word out of it, so the faces drawn *as* stencils -- the
  ones with the little breaks already in the letters, which is how the middle
  of an O stays attached -- are the best thing you can cut and the worst thing
  you can weld.  Set "Freddie" in one at 20 mm and the weld leaves the breaks
  open: fifteen to seventeen pieces go in, and a name held together by five to
  nine bridges comes out.  Those
  faces say ("stencil",) here and the keyring never offers them; the rest say
  both, and carry the three numbers above.  A stencil uses none of the three --
  it neither welds nor kerns by ink -- so a stencil-only face leaves them None.

Everything here ships in src/fonts next to the code, for the same reason the
sans always did: a hosted function is guaranteed to carry its source and not
necessarily anything else, and Vercel has no system fonts at all.  Each face's
licence sits beside it -- ten of the eleven are under the SIL Open Font
Licence, Chewy is Apache 2.0.
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

BOTH = ("name", "stencil")

# key -> what the page shows, what it sets in, what it is offered for, and what
# the keyring needs of it.
FACES = {
    "sans": dict(
        label="Sans",
        font="Liberation Sans Bold",
        note="Plain and heavy.  The one that fits any name and any length.",
        file=None,                  # the search above, so a system copy will do
        kinds=BOTH, weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Steve Matteson / Ascender Corp."),
    "geometric": dict(
        label="Geometric",
        font="Poppins Bold",
        note="Circular bowls and a single-storey a -- the widest counters "
             "here, and the one that holds up smallest after the sans.",
        file="Poppins-Bold.ttf",
        kinds=BOTH, weld=0.5, gap=-0.15, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, Indian Type Foundry, "
                "Jonny Pinhorn, Ninad Kale"),
    "rounded": dict(
        label="Rounded",
        font="Chewy",
        note="Soft and bouncy, drawn with a fat marker.  Latin-1 only, so no "
             "Polish or Turkish accents.",
        file="Chewy-Regular.ttf",
        kinds=BOTH, weld=0.4, gap=-0.15, min_cap=16.0,
        licence="Apache Licence 2.0, Sideshow (Font Diner)"),
    "script": dict(
        label="Script",
        font="Pacifico",
        note="A brush script.  The letters run into each other before the "
             "weld is asked to do anything, which is what a name keyring "
             "usually wants -- but its lower case is small for its capitals, "
             "so it needs more height than any face here but the heavy.",
        file="Pacifico-Regular.ttf",
        kinds=BOTH, weld=0.4, gap=-0.15, min_cap=20.0,
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
        kinds=BOTH, weld=0.35, gap=0.25, min_cap=18.0,
        licence="SIL Open Font Licence 1.1, JM Sole"),
    "condensed": dict(
        label="Condensed",
        font="Bebas Neue",
        note="Tall narrow capitals -- lower case comes out as capitals too.  "
             "The one for a long name, at about two thirds the width.",
        file="BebasNeue-Regular.ttf",
        # all stems: without a gap the I in FREDDIE welds into the E beside it
        kinds=BOTH, weld=0.4, gap=0.3, min_cap=16.0,
        licence="SIL Open Font Licence 1.1, Ryoichi Tsunekawa"),
    "wide": dict(
        label="Wide",
        font="Archivo Black",
        note="A wide, flat-sided grotesque with the heaviest strokes of the "
             "faces that still hold their counters small.  On a stencil it is "
             "the broad cut; on a keyring it is the sans with the air taken "
             "out of it.",
        file="ArchivoBlack-Regular.ttf",
        # heavy and tightly fitted: at -0.15 mm one stem is inside the last
        # one over the whole cap height, which is one stem rather than two
        kinds=BOTH, weld=0.4, gap=0.25, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, Omnibus-Type"),
    "heavy": dict(
        label="Heavy",
        font="Anton",
        note="The heaviest here and narrow with it: the widest cut and the "
             "most open plate of any of them, at about two thirds the width "
             "of the sans, and with real lower case unlike the condensed.  "
             "Its e is a slot, so a keyring in it wants a tall letter.",
        file="Anton-Regular.ttf",
        kinds=BOTH, weld=0.35, gap=0.25, min_cap=21.0,
        licence="SIL Open Font Licence 1.1, the Anton Project Authors"),
    # ---- drawn as stencils: the breaks are in the letters already ----------
    "stencil": dict(
        label="Stencil",
        font="Saira Stencil One",
        note="A stencil face: the breaks are drawn into the letters, so the "
             "middle of an O is already tied to the plate and nothing needs "
             "bridging.  The one to reach for first.",
        file="SairaStencilOne-Regular.ttf",
        kinds=("stencil",), weld=None, gap=None, min_cap=None,
        licence="SIL Open Font Licence 1.1, Omnibus-Type"),
    "military": dict(
        label="Military",
        font="Black Ops One",
        note="Stencilled army-crate capitals, breaks and all -- rough-edged "
             "where the others are clean.  No bridges either.",
        file="BlackOpsOne-Regular.ttf",
        kinds=("stencil",), weld=None, gap=None, min_cap=None,
        licence="SIL Open Font Licence 1.1, the Black Ops Project Authors"),
    "crate": dict(
        label="Crate",
        font="Stardos Stencil Bold",
        note="The lightest of the stencil faces, the one stamped on a packing "
             "case.  Its strokes are thin: a short word or a big plate, or "
             "the readout will tell you the cut is finer than your nozzle.  "
             "Latin-1 only, so no Polish or Turkish accents.",
        file="StardosStencil-Bold.ttf",
        kinds=("stencil",), weld=None, gap=None, min_cap=None,
        licence="SIL Open Font Licence 1.1, Vernon Adams"),
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


def offered(kind="name"):
    """The faces one kind of object is offered, in the order to show them.

    Anything that is not a stencil is asking as a keyring does -- a card and a
    fob set their lettering the same way, small and welded to nothing -- so
    "name" is what everything else looks up.
    """
    want = "stencil" if kind == "stencil" else "name"
    return {k: v for k, v in FACES.items() if want in v["kinds"]}


def check(key, kind):
    """`key` if that face is offered for `kind`, else an error saying so.

    A stencil face on a keyring is not a near miss to be rounded off quietly:
    the breaks drawn into its letters survive the weld, and the word comes out
    as a heap of fragments on bridges.  Better to say which faces there are.
    """
    want = "stencil" if kind == "stencil" else "name"
    if key in FACES and want not in FACES[key]["kinds"]:
        raise ValueError(
            f"{FACES[key]['font']} is for stencils, not for a {kind} -- its "
            f"letters are drawn with breaks in them, which a keyring would "
            f"weld into fragments.  The faces for this are "
            + ", ".join(offered(kind)))
    return key


def face(value=None, kind=None):
    """The face `value` names, as a dict with a `path` on it.

    `value` is a key from FACES, or a path to a TTF of your own -- the command
    line takes either, the browser only the keys, since a path in a request is
    a request to read a file off the server.  An outside font has no measured
    weld or minimum height, so those come back None and nametag falls back to
    its own constants.

    `kind` is what it is being set in, and a face that is not offered for that
    is an error rather than a substitution.  A path of your own is nobody's
    business but yours: it is not checked against anything.
    """
    key = value or DEFAULT
    if kind is not None:
        check(key, kind)
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

