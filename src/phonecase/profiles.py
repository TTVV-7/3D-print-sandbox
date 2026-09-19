"""Printers, filaments, palettes and case presets.

Separate from the geometry for the same reason as in the lamp: the case is a
shape, and how hot to run it and which slot the coral is in are a different
question that changes per machine and per spool.

About the tool change macros. They are the one part of this file that cannot
be checked from here. ``T0``..``Tn`` is what Marlin, RepRap, Klipper and
Prusa firmware act on, and the Bambu profile wraps it in the ``M620``/``M621``
AMS pair that their own output uses. If your machine wants something else,
set ``tool_change`` rather than editing the writer -- and either way, put one
two-layer test through it before you commit to a six hour print.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .paint import Palette, Slot
from .spec import CaseSpec, PHONES


@dataclass
class Printer:
    name: str = "generic-mmu"
    bed_x: float = 220.0
    bed_y: float = 220.0
    max_z: float = 250.0
    nozzle: float = 0.4
    filament_diameter: float = 1.75
    #: How many AMS / MMU slots are loaded.
    tools: int = 4
    absolute_e: bool = True
    #: ``{tool}`` is the slot number.
    tool_change: str = "T{tool}"
    #: Run after the first tool is selected, not before: priming ahead of the
    #: tool change primes whatever happened to be loaded last.
    prime_gcode: str = """\
G92 E0
G1 Z0.3 F900
G1 X{prime_x0} Y{prime_y} F3000
G1 X{prime_x1} Y{prime_y} E14 F1000
G1 X{prime_x1} Y{prime_y_2} E15 F1000
G92 E0
G1 Z2 F900
"""
    start_gcode: str = """\
M190 S{bed}
M104 S{nozzle_temp}
G28
G29 ; mesh bed levelling -- delete this line if your printer has no probe
M109 S{nozzle_temp}
G92 E0
"""
    end_gcode: str = """\
M107
G91
G1 Z10 E-4 F900
G90
G1 X5 Y{bed_y_safe} F4000
M104 S0
M140 S0
M84
"""


@dataclass
class Filament:
    """One material, in however many colours. The colours are the palette."""

    name: str = "pla"
    nozzle_temp: int = 215
    bed_temp: int = 60
    density: float = 1.24
    flow: float = 1.0
    retract_mm: float = 0.8
    retract_speed: int = 2100
    z_hop: float = 0.3
    #: Travels shorter than this are just moves. Solid infill is hundreds of
    #: short hops per layer and retracting across every one of them costs
    #: time and leaves the nozzle to ooze on the way back in.
    retract_min: float = 2.0
    #: Volume flushed through the nozzle at every tool change (mm^3). This is
    #: the number that decides how much of a spool ends up in the bin.
    purge_mm3: float = 110.0
    #: mm/s
    first_layer_speed: float = 20.0
    perimeter_speed: float = 40.0
    outer_speed: float = 28.0
    infill_speed: float = 55.0
    purge_speed: float = 22.0
    travel_speed: float = 180.0
    fan_first_layer: int = 0
    fan: int = 100


PRINTERS: dict[str, Printer] = {
    "generic-mmu": Printer(),
    "bambu-p1s-ams": Printer(
        name="bambu-p1s-ams", bed_x=256, bed_y=256, max_z=256, tools=4,
        # M620/M621 bracket the swap on Bambu firmware; T alone is ignored.
        tool_change="M620 S{tool}A\nT{tool}\nM621 S{tool}A"),
    "bambu-x1c-ams": Printer(
        name="bambu-x1c-ams", bed_x=256, bed_y=256, max_z=256, tools=4,
        tool_change="M620 S{tool}A\nT{tool}\nM621 S{tool}A"),
    "prusa-mk4-mmu3": Printer(
        name="prusa-mk4-mmu3", bed_x=250, bed_y=210, max_z=220, tools=5),
    "voron-350": Printer(name="voron-350", bed_x=350, bed_y=350, max_z=330,
                         tools=4),
}

FILAMENTS: dict[str, Filament] = {
    "pla": Filament(),
    "pla-silk": Filament(name="pla-silk", nozzle_temp=225, outer_speed=24.0,
                         # Silk shows every seam and every under-purge.
                         purge_mm3=160.0),
    "petg": Filament(name="petg", nozzle_temp=240, bed_temp=80, density=1.27,
                     retract_mm=1.4, purge_mm3=150.0, outer_speed=24.0,
                     infill_speed=45.0),
    # TPU is the right material for a case and the wrong one for an AMS.
    # It is here so the geometry can be printed in one colour; do not feed
    # it through a Bowden multi-material path.
    "tpu-95a": Filament(name="tpu-95a", nozzle_temp=230, bed_temp=45,
                        density=1.21, retract_mm=0.2, retract_speed=1200,
                        first_layer_speed=12.0, perimeter_speed=18.0,
                        outer_speed=15.0, infill_speed=20.0,
                        travel_speed=90.0, purge_mm3=250.0),
}


def _pal(*entries: str, base: int = 0) -> Palette:
    return Palette.parse(list(entries), base)


#: Starting points. Slot 0 is the body colour unless the palette says else.
PALETTES: dict[str, Palette] = {
    "mono":     _pal("#2b2f36:graphite"),
    "duo":      _pal("#2b2f36:graphite", "#e4572e:coral"),
    "primary":  _pal("#f4f4f2:bone", "#1b1b1f:ink", "#e03131:red",
                     "#1c7ed6:blue"),
    "sunset":   _pal("#2b2f36:graphite", "#ff6b35:orange", "#f7c59f:sand",
                     "#efefd0:cream"),
    "mint":     _pal("#f8f9fa:snow", "#20c997:mint", "#0b7285:teal",
                     "#212529:ink"),
    "hi-vis":   _pal("#111111:black", "#f2ff00:acid", "#ff2d95:magenta",
                     "#00e5ff:cyan"),
}


def case(model: str, **kw) -> CaseSpec:
    if model not in PHONES:
        raise KeyError(model)
    return CaseSpec(PHONES[model], **kw)


#: Named cases: a fit and a finish, not a shape. The shape comes from the
#: phone. ``snug`` is the one to print first.
CASES: dict[str, dict] = {
    # The default. Enough wall to survive a drop, enough lip to keep the
    # glass off the table, tight enough not to rattle.
    "snug": dict(clearance=0.35, wall=1.7, back_thickness=1.3, lip=1.2,
                 lip_inset=0.9),
    # Thinner everywhere. Prints faster, feels better, protects less.
    "slim": dict(clearance=0.3, wall=1.2, back_thickness=1.0, lip=0.8,
                 lip_inset=0.6),
    # Thicker wall and a taller lip. Noticeably chunkier in the hand.
    "rugged": dict(clearance=0.4, wall=2.4, back_thickness=1.8, lip=2.0,
                   lip_inset=1.2),
    # For a first print on an unfamiliar phone: loose enough that a slightly
    # wrong dimension still goes on.
    "test": dict(clearance=0.5, wall=1.6, back_thickness=1.2, lip=1.0,
                 lip_inset=0.7),
}
