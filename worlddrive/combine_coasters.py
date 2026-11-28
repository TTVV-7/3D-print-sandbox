"""Every four-colour coaster in one 3MF: worlddrive/stl/wd_all_coasters.3mf.

    python3 worlddrive/combine_coasters.py

Reads each coaster's own 3MF (designs.py and infill_coasters.py write them in
Bambu Studio's form, bambu3mf.py) and writes them into one, four across, each
its own object with every colour a part on its extruder: 1 navy, 2 yellow,
3 blue, 4 white. Snapmaker's slicer, Orca and Bambu Studio open it in colour;
Arrange puts them on as many plates as they need.

The logo coaster (wd_coaster_logo) isn't in it: its continents are light blue,
on extruder 4, where these have white. It prints from its own file.
Run this again after rebuilding any of them.
"""
from pathlib import Path

import bambu3mf

HERE = Path(__file__).resolve().parent
COASTERS = [f"wd_infill_{p}{s}" for s in ("_logo", "") for p in ("topo", "honeycomb", "gyroid", "globe")] + [
    "wd_coaster_badge", "wd_coaster_mark"]

if __name__ == "__main__":
    stl = HERE / "stl"
    coasters = [(name, bambu3mf.read(stl / f"{name}.3mf")[0][1]) for name in COASTERS]
    bambu3mf.write(stl / "wd_all_coasters.3mf", coasters)
    print(len(coasters), "coasters in wd_all_coasters.3mf")
