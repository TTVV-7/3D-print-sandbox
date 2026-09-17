"""Measure what a face needs of a keyring, and print the FACES line for it.

The three numbers in `typefaces.FACES` are not all the same kind of number,
and pretending they were is how you get a table that looks measured and is
not.  This says which is which.

  **min_cap is measured.**  It is the shortest letter height at which the weld
  shuts none of a face's counters, and it is found the long way: eight awkward
  names, every height from 10 to 26 mm, every weld that still prints as an
  outline, counting the counters that closed.  Run this over the six faces
  that were measured by hand and it returns their published floors -- five of
  the six to the millimetre, Alfa Slab One two steps high, which is the sweep
  being stricter than the eye was rather than the two disagreeing about what
  happened.  That is the only reason to believe it about a face nobody has
  looked at yet.

  **weld and gap are not.**  Both were tried the same way and neither moves
  anything countable: across all six faces, changing the gap from -0.15 to
  +0.4 alters the counters that close not at all and the bridges by at most
  one, and the weld is the same story.  What they change is how the word
  reads, which is a judgment and is left as one.  They are banded here from
  two things about the face that *can* be measured -- how heavy its stem is
  and how narrow its letters are -- along the lines typefaces.py already gives
  for them: a fat face is most of the way to one piece and wants little weld,
  a face of mostly vertical stems wants daylight between its letters and the
  weld to close it.  A band is a starting point for the eye, not a result.

    python3 src/measure_faces.py                      # every bundled face
    python3 src/measure_faces.py sans script          # just those
    python3 src/measure_faces.py src/fonts/Your.ttf   # one not in FACES yet
    python3 src/measure_faces.py -v sans              # with the whole grid

`-v` prints the counters-shut grid the floor is read off, which is the thing
to look at when a face comes back pinned at the top of the sweep: a face drawn
as four parallel lines has no height at which the weld leaves its counters
alone, and the grid says so in a way the one number cannot.
"""
import sys
from pathlib import Path

from shapely.geometry import LineString
from shapely.ops import unary_union

import cards
import nametag
import typefaces

# The eight names.  They are awkward on purpose: doubled letters that want to
# merge (Abbey, Freddie), round counters that shrink fastest (Oscar, Sophie),
# a dotted i that needs a bridge (Mia, Gigi), ascenders and descenders
# together (Benjamin), and one short enough that there is nothing to hide
# behind (Mia).
NAMES = ["Mia", "Abbey", "Freddie", "Oscar", "Noah", "Sophie", "Gigi", "Benjamin"]

# The heights the app's slider offers, which is the range worth knowing about.
CAP_LO, CAP_HI, CAP_STEP = 10.0, 26.0, 1.0

# The welds that still print as an outline.  Under 0.35 the ring the weld
# leaves round the letters is thinner than one line of a 0.4 mm nozzle and
# stops printing as an outline at all.
WELD_MIN, WELD_MAX, WELD_STEP = 0.35, 0.5, 0.05

# Where the weld and the gap are banded from.  Both ratios are against the cap
# height, so they say something about the face rather than about the size it
# was measured at.
#
#   stem/cap -- how heavy the face is.  Alfa Slab One is 0.36 and wants the
#   least weld of the six; Bebas Neue and Pacifico are near 0.16 and want
#   more.  Over HEAVY the face is most of the way to one piece already.
#
#   width/cap -- how narrow its letters are.  Under NARROW the face is mostly
#   vertical stems, and stems set tight weld into one fat stem.
HEAVY = 0.30
NARROW = 0.52
GAP_TIGHT = -0.15       # letters overlap, which is free when they differ
GAP_CLEAR = 0.3         # daylight, for a face that is all stems
GAP_REACH = 0.25        # slab serifs: one letter's bracket swallows the next

# The height the structural ratios are taken at.  Well clear of the nozzle, so
# the answer is about the letterforms and not about the resolution of the test.
RATIO_CAP = 18.0


def runs(body, y):
    """The ink along a horizontal line through `body`, as (x0, x1) pairs."""
    line = LineString([(body.bounds[0] - 1.0, y), (body.bounds[2] + 1.0, y)])
    cut = body.intersection(line)
    if cut.is_empty:
        return []
    parts = [cut] if cut.geom_type == "LineString" else list(cut.geoms)
    return sorted((g.bounds[0], g.bounds[2]) for g in parts if g.length > 1e-9)


def stem_ratio(font, cap=RATIO_CAP):
    """How heavy the face is: its narrowest upright, over the cap height.

    Taken from the I where there is one, because an I is a stem and nothing
    else.  A face whose I is drawn with a flourish falls back to the narrowest
    stroke in HIN, which is the same measurement with more noise.
    """
    for probe in ("I", "HIN"):
        try:
            shapes = nametag.glyphs(probe, font, cap, 0.0)
        except ValueError:
            continue
        if not shapes:
            continue
        body = unary_union(shapes)
        wide = [x1 - x0 for x0, x1 in runs(body, (body.bounds[1] + body.bounds[3]) / 2.0)]
        if wide:
            return min(wide) / cap
    return 0.2


def width_ratio(font, cap=RATIO_CAP):
    """How narrow its letters are: mean ink width of HAMBONE, over the cap."""
    wide = []
    for ch in "HAMBONE":
        try:
            shapes = nametag.glyphs(ch, font, cap, 0.0)
        except ValueError:
            continue
        if shapes:
            x0, _, x1, _ = cards.extent(shapes)
            wide.append(x1 - x0)
    return (sum(wide) / len(wide) / cap) if wide else 0.6


def band(font):
    """(weld, gap, why) for a face, from how heavy and how narrow it is.

    Banded, not measured -- see the module docstring.  The bands are set so
    the six faces that were done by eye come back close to what they were
    given: heavy faces little weld and room to breathe, narrow faces daylight,
    everything else the tight setting and the full weld.
    """
    stem, width = stem_ratio(font), width_ratio(font)
    why = [f"stem/cap {stem:.3f}", f"width/cap {width:.3f}"]
    if stem >= HEAVY:
        return WELD_MIN, GAP_REACH, why + ["heavy: little weld, serifs reach"]
    if width <= NARROW:
        return 0.4, GAP_CLEAR, why + ["narrow: stems want daylight"]
    if stem >= 0.21:
        return 0.4, GAP_TIGHT, why + ["middling weight"]
    return WELD_MAX, GAP_TIGHT, why + ["light: wants the whole weld"]


def welds():
    out, w = [], WELD_MIN
    while w <= WELD_MAX + 1e-9:
        out.append(round(w, 2))
        w += WELD_STEP
    return out


def caps():
    out, c = [], CAP_LO
    while c <= CAP_HI + 1e-9:
        out.append(round(c, 1))
        c += CAP_STEP
    return out


def sweep(font, gap, verbose=False):
    """(min_cap, grid): the shortest height that shuts no counter at any weld.

    The grid is every (height, weld) against the counters the eight names lost
    there, which is what the floor is read off and what `-v` prints.
    """
    ws, grid = welds(), {}
    for cap in caps():
        for name in NAMES:
            shapes = nametag.glyphs(name, font, cap, gap)
            for w in ws:
                body, _, _ = nametag.weld_together(shapes, w, nametag.BRIDGE)
                grid[cap, w] = grid.get((cap, w), 0) + nametag.shut_counters(shapes, body)
        if verbose:
            print(f"      {cap:4.0f} mm  " + "  ".join(f"{w}:{grid[cap, w]:>2}" for w in ws),
                  file=sys.stderr)
    clean = [c for c in caps() if all(grid[c, w] == 0 for w in ws)]
    return (clean[0] if clean else CAP_HI), grid


def measure(font, verbose=False):
    """(weld, gap, min_cap, notes) for one font file."""
    weld, gap, why = band(font)
    min_cap, grid = sweep(font, gap, verbose)
    notes = []
    if not any(all(grid[c, w] == 0 for w in welds()) for c in caps()):
        notes.append(f"no height under {CAP_HI:g} mm keeps every counter open "
                     f"-- pinned to the top of the sweep")
    if verbose:
        print("      " + ", ".join(why), file=sys.stderr)
    return weld, gap, min_cap, notes


def main(argv):
    verbose = "-v" in argv
    names = [a for a in argv if a != "-v"] or list(typefaces.FACES)
    for a in names:
        path = typefaces.face(a)["path"] if a in typefaces.FACES else a
        print(f"{a}  ({Path(path).name})", file=sys.stderr)
        weld, gap, min_cap, notes = measure(path, verbose)
        known = typefaces.FACES.get(a)
        mark = ""
        if known:
            same = all(abs(known[k] - v) < 1e-9 for k, v in
                       (("weld", weld), ("gap", gap), ("min_cap", min_cap)))
            mark = "   == as written" if same else (
                f"   written weld={known['weld']} gap={known['gap']} "
                f"min_cap={known['min_cap']}")
        print(f"    weld={weld}, gap={gap}, min_cap={min_cap}{mark}"
              + ("   [" + "; ".join(notes) + "]" if notes else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
