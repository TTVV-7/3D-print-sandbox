# World Drive keychains & coasters

![all five](previews/all.png)

`python3 worlddrive/designs.py` rebuilds everything (about 20 s): the flat
artwork in `art/`, the printable files in `stl/` (a 3MF with the colours
already assigned, and a single-colour STL), and the renders in `previews/`.
The parts are made by `src/logocard.py`, the same code as the NFC logo cards.

| File | What | Size |
|---|---|---|
| `wd_mark_keychain` | The globe-and-road mark, die-cut, with a ring tab | 45 × 45 × 3 mm |
| `wd_mark_keychain_nfc` | The same, 50 mm, two halves with a 25 mm NTAG sticker glued between them. Write `https://worlddrive.app` to the tag and a tap opens the game. Tap arcs on the back | 50 × 49 × 3 mm |
| `wd_wordmark_keychain` | The mark plus WORLD / DRIVE on a rounded tag, ring hole on the left | 62 × 28 × 3 mm |
| `wd_coaster_mark` | The mark on a plain navy disc | Ø100 × 4 mm |
| `wd_coaster_badge` | WORLD DRIVE over the top, worlddrive.app underneath, yellow rim | Ø100 × 4 mm |

## Colours: four filaments, one AMS

| Slot | Colour | Used for |
|---|---|---|
| Body | navy `#0b1424` (or black) | the card itself and the keylines |
| | blue `#2b7de0` | the globe |
| | yellow `#ffd23f` | the road, DRIVE, the coaster rim and URL |
| | white | the car, the lane dashes, WORLD |

The colours are flush inlays in the face, so the filament only changes in the
last few layers. They print **artwork face down** on the bed, so a textured
PEI plate gives the faces that texture. No supports.

The mark is a simplified flat-colour redraw of the site's icon so it prints
cleanly. Lines are at least 1 mm wide on the keychains. The fiddly parts are
the lane dashes: on the 45 mm keychain they are about 1 × 2 mm. Use a 0.4 mm
nozzle or smaller. If they come out messy, print the 50 mm or a coaster.

Coasters: put four 10 mm felt or cork dots on the back, or glue a 95 mm cork
disc on it. PETG copes with hot mugs better than PLA does.

To change something, edit `designs.py`: `mark()` is the logo, `DESIGNS` sets
each item's size, ring, NFC, backing and thickness, and the four colours are
at the top.

# Infill coaster set

![the set, plain and with the logo](previews/infill_set.png)

`python3 worlddrive/infill_coasters.py` builds these. They're the open-top
"infill" coasters: a solid floor, a rim, and thin walls standing on the floor
with nothing over them. The pattern is modelled as real walls instead of
relying on a slicer setting, so they print the same with default settings in
any slicer.

| Pattern | Look |
|---|---|
| `honeycomb` | hexagons, 10 mm across |
| `gyroid` | a slice through a gyroid, like the slicer infill |
| `topo` | contour lines of a made-up landscape |
| `globe` | a globe's meridians and parallels, tilted like the logo |

Each one comes plain (`wd_infill_<pattern>`) or with the World Drive mark on
a solid disc in the middle (`wd_infill_<pattern>_logo`).
`wd_infill_set.3mf` and `wd_infill_set_logo.3mf` have all four laid out 2 × 2
on one plate (206 × 206 mm).

- Ø100 mm, 4.8 mm tall: a 1.2 mm floor with walls 3.6 mm high on it.
- The walls are 0.9 mm, two lines of a 0.4 mm nozzle. The biggest open
  pocket is about 16 mm across, so any mug sits on plenty of walls.
- **Colours**: the floor is one filament and the walls another, so the
  plain ones need just one filament change, at 1.2 mm. On a single-nozzle
  printer a pause (M600) at that height does it. The logo ones also use
  blue and white in the top 0.6 mm of the centre disc.
- Good colour pairs: navy floor with yellow walls (as rendered), black with
  silk gold, white with any bright colour, or a translucent floor with an
  opaque pattern.
- **Slicer**: leave the defaults. If your slicer adds "only one wall on top
  surfaces" or ironing, it won't matter, since the walls have no top surface
  wider than 0.9 mm.
- PETG copes with hot mugs better than PLA does.

Edit the numbers at the top of `infill_coasters.py` (`D`, `BASE`, `HEIGHT`,
`WALL`, `RIM`) to change the size. A new pattern is a function returning
shapely lines, plus one line in `PATTERNS`.
