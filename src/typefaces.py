"""The faces a name keyring can be set in.

A keyring is not a page.  The letters are the object, so a face has to hold up
as plastic and not only as a shape, and the three things that decide whether
it does are settled here rather than left to the caller:

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

`min_cap` is not a guess.  It comes from setting "Mia", "Abbey", "Freddie",
"Oscar", "Noah", "Sophie", "Gigi" and "Benjamin" in each face at every height
from 10 to 26 mm and every weld from 0.5 down to 0.35 mm, and counting the
counters that closed: it is the shortest letter at which none of them did, at
any of those welds -- under 0.35 mm the outline the weld leaves round the
letters is thinner than one extrusion line and stops printing as an outline at
all.  src/measure_faces.py is that sweep, and running it over the six plain
faces returns the floors they were given by eye.  A name is welcome to go
under the floor; the readout says what it cost.

`weld` and `gap` are a different kind of number, and the honest thing is to
say so.  Both were put through the same sweep and neither moves anything you
can count: across all six plain faces, taking the gap from -0.15 to +0.4 mm
changes the counters that close not at all and the bridges by at most one, and
the weld behaves the same way.  What they change is how the word reads.  So
they are banded from two things about a face that can be measured -- how heavy
its stem is and how narrow its letters are -- and then left to the eye.

There are forty-one faces: the six plain ones the keyring started with,
twenty-three ornate ones, and twelve that are famous in their own right rather
than imitations of famous ones.  Eight of the thirty-five have a `min_cap` of
26 mm, the top of the sweep, which is the sweep's way of saying that no letter
height on the slider keeps that face's counters open -- a face drawn as four
parallel lines has nothing the weld will leave alone.  They are kept anyway, because the stencil
cuts them straight through a plate where the bridges do the holding, and
because the readout tells the truth about what closed.

Everything here ships in src/fonts next to the code, for the same reason the
sans always did: a hosted function is guaranteed to carry its source and not
necessarily anything else, and Vercel has no system fonts at all.  Licences sit
beside the fonts: Chewy and Special Elite are Apache 2.0, everything else is
under the SIL Open Font Licence -- the five original ones each with their own
file, the twenty-three ornate ones together in LICENSE-Complicated.txt and the
twelve famous ones in LICENSE-Famous.txt, each carrying the licence text once
and every one of their copyright lines.  Orbitron, the one variable font here,
ships exactly as published and is set to its heaviest weight in memory rather
than on disk, so the Reserved Font Name on it stays honest.
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
        group="Plain",
        label="Sans",
        font="Liberation Sans Bold",
        note="Plain and heavy.  The one that fits any name and any length.",
        file=None,                  # the search above, so a system copy will do
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Steve Matteson / Ascender Corp."),
    "geometric": dict(
        group="Plain",
        label="Geometric",
        font="Poppins Bold",
        note="Circular bowls and a single-storey a -- the widest counters "
             "here, and the one that holds up smallest after the sans.",
        file="Poppins-Bold.ttf",
        weld=0.5, gap=-0.15, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, Indian Type Foundry, "
                "Jonny Pinhorn, Ninad Kale"),
    "rounded": dict(
        group="Plain",
        label="Rounded",
        font="Chewy",
        note="Soft and bouncy, drawn with a fat marker.  Latin-1 only, so no "
             "Polish or Turkish accents.",
        file="Chewy-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=16.0,
        licence="Apache Licence 2.0, Sideshow (Font Diner)"),
    "script": dict(
        group="Plain",
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
        group="Plain",
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
        group="Plain",
        label="Condensed",
        font="Bebas Neue",
        note="Tall narrow capitals -- lower case comes out as capitals too.  "
             "The one for a long name, at about two thirds the width.",
        file="BebasNeue-Regular.ttf",
        # all stems: without a gap the I in FREDDIE welds into the E beside it
        weld=0.4, gap=0.3, min_cap=16.0,
        licence="SIL Open Font Licence 1.1, Ryoichi Tsunekawa"),
    # --------------------------------------------------- the complicated ones
    # Twenty-three display faces, all SIL Open Font Licence, all measured the
    # same way as the six above by src/measure_faces.py.  They are here for the
    # stencil as much as for the keyring: a face too fine to weld into a solid
    # word still cuts through a plate, where the bridges do the holding.
    #
    # Seven of them come back pinned at 26 mm -- the top of the sweep -- which
    # means no letter height the slider offers keeps every counter open.  That
    # is a true thing about a face drawn as four parallel lines or as a letter
    # plus its own cast shadow, not a reason to leave it out: the readout says
    # how many closed, and the stencil does not care at all.
    "fraktur": dict(
        group="Blackletter",
        label="Fraktur",
        font="UnifrakturMaguntia",
        note="Broken-stroke blackletter, the Mainz kind, with a hairline on "
             "every curve.  Holds up better than it looks.  Latin-1 only.",
        file="UnifrakturMaguntia-Book.ttf",
        weld=0.5, gap=-0.15, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, j. 'mach' wust"),
    "schwabacher": dict(
        group="Blackletter",
        label="Schwabacher",
        font="UnifrakturCook Bold",
        note="Heavier blackletter with a rounder bowl.  The extra weight costs "
             "height: it wants 17 mm before its counters come back.  Latin-1 only.",
        file="UnifrakturCook-Bold.ttf",
        weld=0.5, gap=-0.15, min_cap=17.0,
        licence="SIL Open Font Licence 1.1, j. 'mach' wust"),
    "pirate": dict(
        group="Blackletter",
        label="Pirate",
        font="Pirata One",
        note="A single-weight blackletter drawn tighter than the others -- the "
             "gothic that sets smallest, and the one for a long name.",
        file="PirataOne-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, Rodrigo Fuenzalida, Nicolas Massi"),
    "rocker": dict(
        group="Blackletter",
        label="Rocker",
        font="New Rocker",
        note="Blackletter with the corners knocked off, halfway to a band "
             "logo.  Softer than the fraktur and about as small.",
        file="NewRocker-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=13.0,
        licence="SIL Open Font Licence 1.1, Pablo Impallari"),
    "medieval": dict(
        group="Blackletter",
        label="Medieval",
        font="MedievalSharp",
        note="A sharp-nibbed medieval hand, and the surprise of the set: it "
             "measures as well as the plain sans, 10 mm with its counters "
             "still holes.",
        file="MedievalSharp.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, wmk69"),
    "quill": dict(
        group="Ornate",
        label="Quill",
        font="Eagle Lake",
        note="Pointed-pen calligraphy with a swelling stroke and a long tail "
             "on half the letters.",
        file="EagleLake-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, Brian J. Bonislawsky (Astigmatic)"),
    "uncial": dict(
        group="Ornate",
        label="Uncial",
        font="Uncial Antiqua",
        note="Round uncial capitals, the shape of an illuminated manuscript.  "
             "Wide, so a long name runs on.",
        file="UncialAntiqua-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=15.0,
        licence="SIL Open Font Licence 1.1, Brian J. Bonislawsky (Astigmatic)"),
    "almendra": dict(
        group="Ornate",
        label="Almendra",
        font="Almendra Display",
        note="An ornate old-style with fine serifs and a swash on the "
             "capitals.  Sets at 10 mm despite the detail.  Latin-1 only.",
        file="AlmendraDisplay-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Ana Sanfelippo"),
    "filigree": dict(
        group="Ornate",
        label="Filigree",
        font="Astloch",
        note="Thin gothic filigree, hairlines throughout.  Its counters hold "
             "open from 11 mm, but the strokes are so fine that the weld is "
             "most of what you actually print, and the letters run together "
             "long before they close up -- one for a short name.  "
             "Latin-1 only.",
        file="Astloch-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=11.0,
        licence="SIL Open Font Licence 1.1, Daniel Rhatigan"),
    "tattoo": dict(
        group="Ornate",
        label="Tattoo",
        font="Miltonian Tattoo",
        note="Fine ornamental tattoo lettering.  It never comes back quite "
             "clean -- a couple of counters close at every height the slider "
             "reaches, which is why it starts at the top -- but a couple is "
             "all it loses.  Latin-1 only.",
        file="MiltonianTattoo-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=26.0,
        licence="SIL Open Font Licence 1.1, Pablo Impallari, Igino Marini"),
    "emblem": dict(
        group="Ornate",
        label="Emblem",
        font="Emblema One",
        note="Heavy inline capitals.  Fat enough that the weld is barely "
             "needed, and it still sets at 10 mm -- the best of the "
             "complicated ones on a small keyring.",
        file="EmblemaOne-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Sorkin Type Co"),
    "nouveau": dict(
        group="Ornate",
        label="Nouveau",
        font="Federant",
        note="Art-nouveau capitals with a flick on every terminal.  Latin-1 only.",
        file="Federant-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Cyreal"),
    "western": dict(
        group="Western",
        label="Western",
        font="Rye",
        note="Wood-type western: heavy slabs with an inline down each stroke.  "
             "The inline is a counter, and the weld shuts it at every height "
             "here -- by far the most of anything in the set -- so what prints "
             "is the solid letter inside the outline rather than the inlined "
             "one.  Latin-1 only.",
        file="Rye-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=26.0,
        licence="SIL Open Font Licence 1.1, Sorkin Type Co"),
    "saloon": dict(
        group="Western",
        label="Saloon",
        font="Sancreek",
        note="Spurred western display, all barbs and brackets.  Wants 22 mm "
             "before it reads as letters rather than as fencing.",
        file="Sancreek-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=22.0,
        licence="SIL Open Font Licence 1.1, The Sancreek Project Authors"),
    "caesar": dict(
        group="Western",
        label="Caesar",
        font="Caesar Dressing",
        note="Roughly chiselled Roman capitals, as though cut with a blunt "
             "tool.  14 mm, the same as the sans's own default.  Latin-1 only.",
        file="CaesarDressing-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=14.0,
        licence="SIL Open Font Licence 1.1, Open Window"),
    "stone": dict(
        group="Western",
        label="Stone",
        font="Piedra",
        note="Letters drawn as cut stone with a crack through each one.  The "
             "cracks are counters, so it wants 20 mm to keep them.  Latin-1 only.",
        file="Piedra-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=20.0,
        licence="SIL Open Font Licence 1.1, Angel Koziupa (Sudtipos)"),
    "drip": dict(
        group="Horror",
        label="Drip",
        font="Nosifer",
        note="Heavy capitals with the paint running off the bottom.  The drips "
             "are separate pieces and the weld catches them, which is exactly "
             "what the weld is for.",
        file="Nosifer-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, Typomondo"),
    "bones": dict(
        group="Horror",
        label="Bones",
        font="Butcherman",
        note="Scratched horror capitals drawn as loose strokes, so its "
             "counters are gaps rather than holes.  It loses a dozen of them "
             "even at the top of the slider, and more than twice that at "
             "10 mm.",
        file="Butcherman-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=26.0,
        licence="SIL Open Font Licence 1.1, Typomondo"),
    "creep": dict(
        group="Horror",
        label="Creep",
        font="Creepster",
        note="Lumpy horror lettering with a dripping crossbar.  22 mm and the "
             "bowls come back.  Latin-1 only.",
        file="Creepster-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=22.0,
        licence="SIL Open Font Licence 1.1, Font Diner, Inc"),
    "metal": dict(
        group="Horror",
        label="Metal",
        font="Metal Mania",
        note="Spiky metal-band lettering drawn as a great many small pieces, "
             "and the slowest of the set to build.  Four counters shut "
             "whatever the height, which is what keeps its floor at the top.  "
             "Latin-1 only.",
        file="MetalMania-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=26.0,
        licence="SIL Open Font Licence 1.1, Open Window"),
    "neon": dict(
        group="Dimensional",
        label="Neon",
        font="Monoton",
        note="Four parallel lines to a stroke, like a neon tube.  The tubes do "
             "survive at the top of the slider -- wind the weld back to 0.35 "
             "and nothing closes at all -- but under 26 mm the weld fills "
             "between them and the letter goes solid.",
        file="Monoton-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=26.0,
        licence="SIL Open Font Licence 1.1, Vernon Adams"),
    "shadow": dict(
        group="Dimensional",
        label="Shadow",
        font="Vast Shadow",
        note="A fat slab with a cast shadow behind it.  The shadow is a second "
             "piece per letter, so the word comes out in more pieces than it "
             "has letters and the bridges do more work than usual -- but the "
             "counters themselves are fine, and it sets at 10 mm.  "
             "Latin-1 only.",
        file="VastShadow-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Sorkin Type Co"),
    "bevel": dict(
        group="Dimensional",
        label="Bevel",
        font="Bungee Shade",
        note="Three-dimensional block capitals with an extruded side.  The "
             "extrusion reads at the top of the slider, at the cost of about "
             "eight counters; below that it fills in and what is left is the "
             "plain block.",
        file="BungeeShade-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=26.0,
        licence="SIL Open Font Licence 1.1, The Bungee Project Authors"),
    # -------------------------------------------------------- the famous ones
    # Twelve faces that are famous themselves rather than imitations of famous
    # ones: the Roman capitals off every film poster, the Didone off every
    # fashion masthead, the arcade cabinet, the terminal, the typewriter.  All
    # free -- eleven under the SIL Open Font Licence and Special Elite under
    # Apache 2.0 -- and none of them a lookalike of anybody's logo, which is
    # the difference that matters when the thing being made is sold.
    "inscribed": dict(
        group="Ornate",
        label="Inscribed",
        font="Cinzel Decorative Black",
        note="Roman inscriptional capitals, the ones cut into monuments and "
             "printed on every other film poster.  Heavy enough at 15 mm.",
        file="CinzelDecorative-Black.ttf",
        weld=0.4, gap=-0.15, min_cap=15.0,
        licence="SIL Open Font Licence 1.1, Natanael Gama"),
    "copperplate": dict(
        group="Ornate",
        label="Copperplate",
        font="Great Vibes",
        note="A formal Spencerian script -- the hand every soft-drink logo is "
             "descended from.  The hairlines between the thick strokes are "
             "what the weld eats, so it never comes back entirely clean and "
             "starts at the top of the slider.",
        file="GreatVibes-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=26.0,
        licence="SIL Open Font Licence 1.1, The Great Vibes Project Authors"),
    "heavy": dict(
        group="Poster",
        label="Heavy",
        font="Anton",
        note="The heaviest condensed grotesque here, and the one every poster "
             "and headline is set in.  So heavy that its counters are slits: "
             "it wants 23 mm, more than the slab does.",
        file="Anton-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=23.0,
        licence="SIL Open Font Licence 1.1, The Anton Project Authors"),
    "didone": dict(
        group="Poster",
        label="Didone",
        font="Abril Fatface",
        note="Fat Didone with hairline serifs, the fashion-masthead letter.  "
             "The hairlines thicken under the weld, which on a keyring is an "
             "improvement.",
        file="AbrilFatface-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=15.0,
        licence="SIL Open Font Licence 1.1, TypeTogether"),
    "bistro": dict(
        group="Poster",
        label="Bistro",
        font="Lobster",
        note="A bold condensed script off a thousand chalkboards and food "
             "trucks.  Its letters already run into each other, so the weld "
             "has little left to do.",
        file="Lobster-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=18.0,
        licence="SIL Open Font Licence 1.1, The Lobster Project Authors"),
    "comic": dict(
        group="Poster",
        label="Comic",
        font="Bangers",
        note="Comic-book lettering, all caps and shouting.  The tight "
             "counters want 21 mm before they read as holes.",
        file="Bangers-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=21.0,
        licence="SIL Open Font Licence 1.1, The Bangers Project Authors"),
    "deco": dict(
        group="Poster",
        label="Deco",
        font="Righteous",
        note="Art-deco capitals with the geometry of a 1930s cinema front.  "
             "Sets at 13 mm, which for a decorative face is small.",
        file="Righteous-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=13.0,
        licence="SIL Open Font Licence 1.1, Brian J. Bonislawsky (Astigmatic)"),
    "arcade": dict(
        group="Machine",
        label="Arcade",
        font="Press Start 2P",
        note="The eight-bit letter off an arcade cabinet, drawn as square "
             "pixels.  Every corner is a right angle and every counter is a "
             "square, which is why it holds up at 11 mm -- the best of the "
             "display faces after Emblem.",
        file="PressStart2P-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=11.0,
        licence="SIL Open Font Licence 1.1, The Press Start 2P Project Authors"),
    "scifi": dict(
        group="Machine",
        label="Sci-fi",
        font="Orbitron Black",
        note="Square geometric capitals, the lettering of every spaceship and "
             "title sequence.  It ships as one variable file from Regular to "
             "Black and is set at Black here, which is the weight that prints; "
             "Latin-1 bar the slashed O.",
        file="Orbitron-Variable.ttf",
        weld=0.4, gap=-0.15, min_cap=12.0,
        licence="SIL Open Font Licence 1.1, The Orbitron Project Authors"),
    "terminal": dict(
        group="Machine",
        label="Terminal",
        font="VT323",
        note="The glowing letter off a DEC VT320 terminal, strokes and all.  "
             "Thin for a keyring: it wants 24 mm, and the weld is most of "
             "what you print at any height.",
        file="VT323-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=24.0,
        licence="SIL Open Font Licence 1.1, The VT323 Project Authors"),
    "typewriter": dict(
        group="Machine",
        label="Typewriter",
        font="Special Elite",
        note="A typewriter face with the ink knocked about, the letter of "
             "every case file and ransom note.  The battering is made of "
             "notches finer than a nozzle, so some of them close at any "
             "height -- what survives still reads as a typewriter.",
        file="SpecialElite-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=26.0,
        licence="Apache Licence 2.0, Astigmatic (AOETI)"),
    "military": dict(
        group="Machine",
        label="Military",
        font="Black Ops One",
        note="Stencilled military capitals with the breaks already drawn in.  "
             "That is this program's trick done in the letterform, and it is "
             "why it sets at 10 mm and why it cuts as a stencil with barely a "
             "bridge.",
        file="BlackOpsOne-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, The Black Ops Project Authors"),
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

