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

There are forty-eight faces: the six plain ones the keyring started with, and
forty-two display faces for when a name wants to be a thing rather than a
label.  Six of the forty-two have a `min_cap` of 26 mm, the top of the
sweep, which is the sweep's way of saying that no letter height on the slider
keeps that face's counters open -- a face drawn as four parallel lines has
nothing the weld will leave alone.  They are kept anyway, because the stencil
cuts them straight through a plate where the bridges do the holding, and
because the readout tells the truth about what closed.

Everything here ships in src/fonts next to the code, for the same reason the
sans always did: a hosted function is guaranteed to carry its source and not
necessarily anything else, and Vercel has no system fonts at all.  Licences sit
beside the fonts: Chewy, Luckiest Guy and Permanent Marker are Apache 2.0 and
each have their own file, everything else is under the SIL Open Font Licence --
the five original ones each with their own file too, the forty OFL display
faces together in LICENSE-Complicated.txt, which carries the licence text once
and every one of their copyright lines.
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
    # Forty-two display faces, all but two SIL Open Font Licence, all measured
    # the same way as the six above by src/measure_faces.py.  They are here for the
    # stencil as much as for the keyring: a face too fine to weld into a solid
    # word still cuts through a plate, where the bridges do the holding.
    #
    # Six of them come back pinned at 26 mm -- the top of the sweep -- which
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
    "roman": dict(
        group="Ornate",
        label="Roman",
        font="Cinzel Decorative",
        note="Classical Roman capitals with a swash and a leaf on the "
             "terminals, the lettering off a monument.  10 mm.",
        file="CinzelDecorative-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Natanael Gama"),
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
    "varsity": dict(
        group="Western",
        label="Varsity",
        font="Graduate",
        note="Collegiate slab, the letter off an American jacket.  The one "
             "face in this group that sets at 10 mm -- the rest of the "
             "western faces are inlined or spurred and pay for it.",
        file="Graduate-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, The Graduate Project Authors"),
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
    # ------------------------------------------------------ nineteen more
    # Added in the same way as the twenty-three above and measured by the same
    # sweep, which had opinions.  Two of them are worth reading before you pick
    # by eye:
    #
    # The stencil faces measure as well as the plain sans -- 10 mm, all three.
    # That is not a fluke and it is not because they are heavy.  A stencil
    # breaks the wall of every counter, so the counter is not an enclosed hole
    # at all but a bay open to the outside, and the weld that shuts a normal
    # face's `a` has nothing there to shut.  The feature that makes them look
    # fragile is what makes them print.
    #
    # The fat comic faces measure worst in the whole set -- Titan One at 24 mm,
    # Luckiest Guy at 22, Bangers at 21 -- which is the opposite of what they
    # look like.  Weight is not the thing; the ratio of counter to stroke is.
    # A face drawn with a very fat marker has small counters by construction,
    # and small counters are what the weld eats first.  Bowlby One is the one
    # that got away with it at 13 mm, because its bowls stayed round holes
    # rather than narrowing to slots.
    "comic": dict(
        group="Comic",
        label="Comic",
        font="Bangers",
        note="Brush-drawn comic lettering on a slant, the sound-effect face.  "
             "Heavy, but its counters are small for the weight, so it wants "
             "21 mm -- more than most of the ornate faces do.",
        file="Bangers-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=21.0,
        licence="SIL Open Font Licence 1.1, The Bangers Project Authors"),
    "titan": dict(
        group="Comic",
        label="Titan",
        font="Titan One",
        note="Fat rounded poster capitals with almost no daylight in them.  "
             "The hungriest face here: 24 mm before its bowls survive the "
             "weld, so it is one for a short name set large.  Latin-1 only.",
        file="TitanOne-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=24.0,
        licence="SIL Open Font Licence 1.1, Rodrigo Fuenzalida"),
    "lucky": dict(
        group="Comic",
        label="Lucky",
        font="Luckiest Guy",
        note="Comic-book capitals, the ones on the cover rather than in the "
             "speech bubble.  22 mm, for the same reason as Titan One.",
        file="LuckiestGuy-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=22.0,
        licence="Apache Licence 2.0, Brian J. Bonislawsky (Astigmatic)"),
    "chunky": dict(
        group="Comic",
        label="Chunky",
        font="Bowlby One",
        note="Heavy grotesque with round bowls, and the one comic face that "
             "sets small -- 13 mm, because its counters stayed holes instead "
             "of narrowing to slots.  The pick of the group for a keyring.  "
             "Latin-1 only.",
        file="BowlbyOne-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=13.0,
        licence="SIL Open Font Licence 1.1, Vernon Adams"),
    "marker": dict(
        group="Comic",
        label="Marker",
        font="Permanent Marker",
        note="Felt-tip handwriting with a dry edge to every stroke.  The "
             "letters lean into each other before the weld is asked for "
             "anything, the way the script does.  Latin-1 only.",
        file="PermanentMarker-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=18.0,
        licence="Apache Licence 2.0, Font Diner, Inc"),
    "stencil": dict(
        group="Stencil",
        label="Stencil",
        font="Stardos Stencil",
        note="A serif cut into stencil strips.  Ties the plain sans at 10 mm, "
             "the best in the set outside Plain, because a broken counter is "
             "open to the outside and the weld cannot close it.  Its breaks "
             "are fine, though, so they read better on the stencil plate than "
             "on a small keyring.  Latin-1 only.",
        file="StardosStencil-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Vernon Adams"),
    "spray": dict(
        group="Stencil",
        label="Spray",
        font="Saira Stencil One",
        note="Heavier stencil with wide breaks you can see at any size -- the "
             "one to pick if you want the stencil to read as a stencil.  "
             "10 mm, on the same trick.",
        file="SairaStencilOne-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, The Saira Stencil Project Authors"),
    "military": dict(
        group="Stencil",
        label="Military",
        font="Black Ops One",
        note="Stencilled military slab, the kind sprayed on a crate.  Fat "
             "enough that the weld is barely needed and broken enough that it "
             "would not matter: 10 mm.",
        file="BlackOpsOne-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, The Black-Ops Project Authors"),
    "retro": dict(
        group="Retro",
        label="Retro",
        font="Lobster",
        note="The retro sign script, bold and connected.  Runs together on "
             "its own like Pacifico but with tighter counters, so it needs "
             "18 mm rather than 20.",
        file="Lobster-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=18.0,
        licence="SIL Open Font Licence 1.1, The Lobster Project Authors"),
    "deco": dict(
        group="Retro",
        label="Deco",
        font="Righteous",
        note="Geometric deco capitals with clipped corners.  13 mm, and one "
             "of the few display faces that stays legible at the bottom of "
             "the slider.",
        file="Righteous-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=13.0,
        licence="SIL Open Font Licence 1.1, Brian J. Bonislawsky (Astigmatic)"),
    "marquee": dict(
        group="Retro",
        label="Marquee",
        font="Limelight",
        note="High-contrast deco display, the lettering on a theatre front.  "
             "Sets at 10 mm despite the hairlines, because what it has "
             "instead of small counters is large ones.",
        file="Limelight-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Sorkin Type Co"),
    "groovy": dict(
        group="Retro",
        label="Groovy",
        font="Shrikhand",
        note="Heavy slanted display with a seventies bulge to every curve.  "
             "16 mm.",
        file="Shrikhand-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=16.0,
        licence="SIL Open Font Licence 1.1, Jonny Pinhorn"),
    "racing": dict(
        group="Retro",
        label="Racing",
        font="Racing Sans One",
        note="Italic speed-lettering off the side of a car.  The slant means "
             "no two letters meet square, which is exactly the case the "
             "negative gap is for.  11 mm.",
        file="RacingSansOne-Regular.ttf",
        weld=0.35, gap=0.25, min_cap=11.0,
        licence="SIL Open Font Licence 1.1, Pablo Impallari, "
                "Rodrigo Fuenzalida"),
    "orbit": dict(
        group="Tech",
        label="Orbit",
        font="Orbitron",
        note="Wide geometric science-fiction capitals.  Shipped as the "
             "variable font Google publishes, unmodified, so what you get is "
             "its regular weight -- which measured better than a heavy "
             "instance of it did, 10 mm against 12.  Latin-1 only.",
        file="Orbitron[wght].ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, The Orbitron Project Authors"),
    "techno": dict(
        group="Tech",
        label="Techno",
        font="Audiowide",
        note="Rounded techno capitals with a slot cut in the heavy strokes.  "
             "10 mm.",
        file="Audiowide-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, Brian J. Bonislawsky (Astigmatic)"),
    "arcade": dict(
        group="Tech",
        label="Arcade",
        font="Press Start 2P",
        note="An eight-bit face, every stroke a whole number of pixels wide.  "
             "Its counters are square, and a square shrinks evenly where a "
             "round bowl pinches at the ends, which is why a face made of "
             "blocks measures better than the fat ones do -- 11 mm.  Sets "
             "wide: a long name runs on.",
        file="PressStart2P-Regular.ttf",
        weld=0.4, gap=-0.15, min_cap=11.0,
        licence="SIL Open Font Licence 1.1, The Press Start 2P Project "
                "Authors"),
    "pixel": dict(
        group="Tech",
        label="Pixel",
        font="Silkscreen",
        note="A smaller, tighter pixel face than the arcade one, drawn for a "
             "screen that did not have many.  10 mm.  Latin-1 only.",
        file="Silkscreen-Regular.ttf",
        weld=0.5, gap=-0.15, min_cap=10.0,
        licence="SIL Open Font Licence 1.1, The Silkscreen Project Authors"),
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

