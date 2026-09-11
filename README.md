# Car-brand valve caps

Schrader valve stem caps with a car maker's emblem on top. Honda, BMW,
Mercedes and Toyota, all off the same parametric cap body.

| | |
|---|---|
| ![flat top](previews/honda_valve_cap_flat_top.png) | ![flat top from above](previews/honda_valve_cap_flat_top_top.png) |

## The caps

The **flat top** is the main one: Ø14.0 × 13.1 mm, knurled, flat face with the
emblem raised 0.6 mm so a single filament change prints the logo in a second
colour.

| STL | Emblem width | Narrowest stroke |
|---|---|---|
| `stl/honda_valve_cap_flat_top.stl` | 11.9 mm | 0.59 mm |
| `stl/bmw_valve_cap_flat_top.stl` | 13.1 mm | 1.01 mm |
| `stl/mercedes_valve_cap_flat_top.stl` | 13.1 mm | 0.75 mm |
| `stl/toyota_valve_cap_flat_top.stl` | 13.1 mm | 0.57 mm |

Honda runs narrower than the rest because its mark is a wide rounded rectangle
whose corners hit the edge of the flat face first; the round marks fill more of
the top. Two more shapes exist for Honda:

| STL | Size (mm) | What it is |
|---|---|---|
| `stl/honda_valve_cap_flat_top_engraved.stl` | Ø14.0 × 12.5 | Same cap with the emblem **recessed 0.5 mm** — for paint fill, or a subtler look. |
| `stl/honda_valve_cap_badge.stl` | 15.0 × 12.2 × 13.2 | Ø11.6 knurled body flaring into an **emblem-shaped badge plate** with the logo raised on it. |

The badge shape only earns its keep when the mark has a distinctive silhouette.
For a circular logo the plate is just a circle, which is the flat top with extra
steps — so BMW and Mercedes don't get one.

`previews/` has an isometric, a top-down and a cutaway render of each.

## About the emblems

Honda is traced from the supplied `honda_logo.glb`. The other three are built
from primitives in `src/logos.py` — circles, ellipses, wedges and bars — which
is both easier and better than tracing a mesh: the symmetry is exact, and every
stroke width is a number you can turn up until it prints cleanly.

Two deliberate departures from the real marks:

- **BMW** has no lettering in the outer band. At 13 mm across it would be
  under a millimetre tall — a smear, not text. The raised parts are the band
  plus two diagonally opposite quarters, so the filament change gives you the
  quartered roundel rather than a flat outline.
- **Toyota**'s inner T sits a little further off the outer ellipse than in the
  real logo, opening the tightest gap from 0.24 mm to 0.40 mm so a 0.4 mm
  nozzle still resolves it as a gap instead of welding it shut.

## The thread

The bore is the real **Schrader valve stem thread: 0.305"-32 UNS** (what's on a
TR413 and every other standard car/truck rubber snap-in stem):

- major Ø 7.747 mm, pitch 0.79375 mm (32 TPI), 60° UN profile
- cut with a uniform **0.15 mm radial clearance**, so the cap's thread crests
  sit at Ø7.19 and its roots at Ø8.05
- ~9 mm of engagement (≈11 turns) plus a 45° lead-in chamfer at the mouth

If it binds on your printer, raise `THREAD_CLEARANCE` in `src/generate.py` to
0.20 and re-run. If it's sloppy, drop it to 0.10.

> These are decorative caps, not sealing caps. The valve core holds the air;
> a cap keeps dirt out. Don't rely on it for pressure.

## Printing

**Orientation:** logo face **down on the build plate**, open threaded end up.
No supports needed either way, but face-down gives the crispest logo — the
0.6 mm-wide bars get the build-plate finish instead of being 4 thin top layers.
Flipping it (emblem up) is also fine and looks better if you care more about
the knurling.

**Settings**

- Layer height **0.12–0.15 mm**. The thread pitch is only 0.794 mm, so 0.2 mm
  layers give you ~4 layers per turn and a mushy thread.
- 3–4 perimeters, 25%+ infill. Each cap is ~1.1–1.4 cm³, so it's a few minutes
  and a gram of filament.
- 0.4 mm nozzle is fine, but enable thin-wall / "detect thin walls" so the
  slicer doesn't drop the narrow strokes — see the table above for the
  narrowest one in each mark (0.57 mm at worst).

**Material:** PETG, ASA or nylon. A wheel well in summer sun gets well past
PLA's softening point, and PLA also goes brittle with UV — it'll crack and you
lose the cap. ASA is the nicest of the three outdoors.

**Two colours without a multi-material printer:** insert a filament change at
**Z = 12.50 mm** — every cap here puts its top face at exactly that height —
and everything above it, the raised emblem, prints in the second colour.
Printing logo-face-down instead, start in the emblem colour and change at
Z = 0.60 mm (flat top) / 0.70 mm (badge). To get the whole top disc in the
second colour rather than just the logo, print emblem-up and move the change
down a millimetre or so.

For the engraved version, print it in one colour and wipe acrylic paint or a
paint pen into the recess, then scrape the top flat with a card once it skins over.

## Regenerating

```
pip install numpy trimesh manifold3d shapely mapbox_earcut networkx pillow scipy
python3 src/generate.py     # writes stl/
python3 src/render.py       # writes previews/
```

Everything is driven by the constants at the top of `src/generate.py` — cap
diameter, height, flute count and depth, per-brand emblem width, how far the
logo stands proud, thread clearance. `BUILDS` lists which brand/variant pairs
get written; any brand can use any variant. Change and re-run; the whole set
takes about ten seconds.

`src/logo_outline.json` is the Honda silhouette (exterior ring + 4 holes)
pulled out of the source `.glb` by `src/extract_outline.py`. The `.glb` itself
isn't committed (it's a 7 MB third-party model); to regenerate the outline:

```
python3 src/extract_outline.py path/to/honda_logo.glb
```

### Adding a brand

Write a builder in `src/logos.py` returning a list of shapely polygons — the
strokes of the mark — normalised to an overall width of 2.0, register it in
`LOGOS`, add a width to `EMBLEM_W` and a line to `BUILDS`.

Return the strokes *separately* rather than pre-unioning them. A shapely union
of touching strokes is "valid" but its boundary touches itself where they meet,
and extruding that gives a non-watertight mesh; `generate.py` extrudes each
stroke and lets the boolean engine weld them, which is robust. `build_flat()`
checks the emblem fits inside the flat face and refuses to emit a cap if not.

These are manufacturer trademarks — caps for your own car, not for selling.
