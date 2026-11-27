# Excavator bucket key holder: SWC edition

![bucket](bucket.png)

`bucket.3mf` is a two-colour print, yellow and black, that opens with each part
on its own filament in Bambu Studio, Orca and PrusaSlicer. `make_bucket.py`
rebuilds it: `python3 keyholders/make_bucket.py`.

This is v2 of the bucket from the Weave-Trial repo (`keyholders/`), whose
teeth snapped off at the root.

## Why the teeth snapped, and what changed

In v1 each black tooth was cut flush against the yellow bucket. All that held
a tooth on was a ~13 x 6 mm face where the two filaments met, lying flat in a
single layer, right where a hanging key bends the tooth hardest.

| | v1 | v2 |
|---|---|---|
| Tooth root | butt joint to yellow, one layer | continuous black, grown out of a full-width black cutting-edge plate |
| Black/yellow seam | 5 x ~78 mm², flat in a layer | lap joint plus side plates, ~3,000 mm², mostly upright walls that bond within each layer |
| Root section | ~13 x 6 mm | ~16 x 11.5 mm with an adapter strap over the lip, ~4x the bending strength |
| Cutting edge | 7 mm | 9 mm |
| Reinforcement | none | 2 mm pin channel down each tooth |

**Pin channels.** Each tooth has a 2 mm hole from its blunt tip, 54 mm back
into the plate. After printing, push in a 2 mm nail, or a length of 1.75 mm
filament with a drop of CA glue, and snip it flush. Even left empty, the hole
gets its own walls from the slicer, which stiffens the tooth.

## Slicer settings

- 4–5 walls and 25–40% gyroid infill. The walls do most of the work.
- Print on its back, as the file is laid out. No supports.
- PETG is tougher than PLA for the teeth. In PLA, a slightly hotter nozzle
  and less part cooling on the teeth improve layer bonding.

## Artwork

All the artwork is inlaid 0.6 mm and flush with the surface:

- the black **SWC** monogram and SOUTHWEST CONTRACTING on the yellow back wall
- black topographic contour lines on the back wall and both side plates
- yellow contour lines on the black cutting-edge plate, between the teeth

The keyholes moved out to ±52 mm, 104 mm apart, to make room for the logo.
The side plates are upright in the print, so their lines change colour on
every layer there. That's free on a tool changer, but costs purge on an AMS.
Set `SEED` for a different hill, and `LOGO` and `TAGLINE` for the lettering.
