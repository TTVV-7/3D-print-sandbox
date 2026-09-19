"""Parametric iPhone case, painted on the outside with an AMS or MMU."""

from .spec import CaseSpec, Cutout, Phone, PHONES, check_case
from .paint import Palette, PaintPlan, Slot, plan
from .profiles import CASES, FILAMENTS, PALETTES, PRINTERS, Filament, Printer
from .svgart import Art, load as load_svg, load_file as load_svg_file
from .toolpath import CasePath, build, stats
from .gcode import plan_tower, tower_stats, write

__all__ = [
    "CaseSpec", "Cutout", "Phone", "PHONES", "check_case",
    "Palette", "PaintPlan", "Slot", "plan",
    "CASES", "FILAMENTS", "PALETTES", "PRINTERS", "Filament", "Printer",
    "Art", "load_svg", "load_svg_file",
    "CasePath", "build", "stats", "plan_tower", "tower_stats", "write",
]
