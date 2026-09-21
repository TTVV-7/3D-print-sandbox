"""Build the case's toolpath, layer by layer, with a colour on every run.

Each layer is a distance field (see :mod:`phonecase.shapes`), each perimeter
is a contour of it, and the solid back plate is contours plus rectilinear
infill. Then every run is cut into colour runs against the paint plan and the
layer is reordered so each filament is used once and once only. That
reordering is worth more than it looks: a tool change on an AMS costs a purge
of roughly a gram, so a layer that changes colour six times instead of three
doubles the waste and the print time.

Two choices that are not the obvious ones:

* Wall perimeters are spaced ``wall / perimeters`` rather than one line width
  apart, so whatever wall thickness you ask for is filled exactly -- no void
  up the middle of a 1.7 mm wall, no over-packed wall that bows out.
* Only the outermost perimeter is painted on the sides, and only the first
  ``art_layers`` of the back plate are painted at all. Everything under the
  skin is the body colour, because nobody can see it and every colour change
  down there is another gram in the purge bin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .paint import PaintPlan, split
from .shapes import Field, RRect, Section
from .spec import CaseSpec, Cutout


@dataclass
class Run:
    """One continuous extrusion in one colour."""

    pts: list[tuple[float, float]]
    z: float
    height: float
    width: float
    kind: str          # skirt | brim | wall | wall-outer | plate | infill
    slot: int
    closed: bool = False

    def length(self) -> float:
        n = len(self.pts)
        total = sum(math.dist(self.pts[i], self.pts[i + 1]) for i in range(n - 1))
        if self.closed and n > 2:
            total += math.dist(self.pts[-1], self.pts[0])
        return total


@dataclass
class Layer:
    index: int
    z: float
    height: float
    runs: list[Run] = field(default_factory=list)

    @property
    def slots(self) -> list[int]:
        """Slots in the order they are used, one entry per tool change."""
        out: list[int] = []
        for r in self.runs:
            if not out or out[-1] != r.slot:
                out.append(r.slot)
        return out


@dataclass
class CasePath:
    spec: CaseSpec
    layers: list[Layer] = field(default_factory=list)

    def tool_changes(self) -> int:
        n = 0
        last = None
        for layer in self.layers:
            for s in layer.slots:
                if s != last:
                    n += 1
                last = s
        return n


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------

def _hole_at(c: Cutout, spec: CaseSpec, z: float) -> RRect | None:
    """The footprint of one cutout at height ``z``, or None if it is not there."""
    if c.face == "back":
        return (RRect(c.u, c.v, c.w / 2, c.h / 2, c.r)
                if z < spec.back_thickness else None)

    # A side cutout is a rounded rectangle in the unrolled (u, z) plane, so
    # at a given z it is a plain slot whose half-width follows the rounding.
    # It is stopped flat at the back plate rather than allowed to cut into
    # it: a hole through the plate edge would leave nothing holding the two
    # halves of the wall together.
    lo = max(c.v - c.h / 2, spec.back_thickness)
    hi = c.v + c.h / 2
    if not (lo - 1e-9 <= z <= hi + 1e-9):
        return None
    flat = c.h / 2 - c.r
    dz = abs(z - c.v)
    if dz <= flat:
        half = c.w / 2
    else:
        k = c.r * c.r - (dz - flat) ** 2
        if k <= 0:
            return None
        half = c.w / 2 - c.r + math.sqrt(k)
    if half <= 1e-6:
        return None

    # Deep enough to punch right through the wall from either direction.
    deep = spec.wall + 2.0
    if c.face == "bottom":
        return RRect(c.u, -spec.outer_l / 2, half, deep, 0.0)
    if c.face == "top":
        return RRect(c.u, spec.outer_l / 2, half, deep, 0.0)
    if c.face == "left":
        return RRect(-spec.outer_w / 2, c.u, deep, half, 0.0)
    return RRect(spec.outer_w / 2, c.u, deep, half, 0.0)


def section_at(spec: CaseSpec, z: float) -> Section:
    """The solid cross-section of the case at height ``z``."""
    oi = spec.outer_inset_at(z)
    outer = RRect(0, 0, spec.outer_w / 2 - oi, spec.outer_l / 2 - oi,
                  max(0.1, spec.outer_r - oi))
    cavity = None
    if z > spec.back_thickness:
        ii = spec.inner_inset_at(z)
        cavity = RRect(0, 0, spec.inner_w / 2 - ii, spec.inner_l / 2 - ii,
                       max(0.1, spec.inner_r - ii))
    holes = tuple(h for h in (_hole_at(c, spec, z) for c in spec.cutouts)
                  if h is not None)
    return Section(outer, cavity, holes)


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def build(spec: CaseSpec, plan: PaintPlan, *, wrap: bool = False,
          brim: int = 0, skirt: int = 1, skirt_gap: float = 2.5,
          test_fit: float | None = None,
          max_layers: int | None = None) -> CasePath:
    """Generate the whole toolpath.

    ``max_layers`` stops after that many layers. It is for previewing rather
    than printing: the back of the case is decided by the artwork layers, so
    building two of them answers what the finished thing looks like in a
    fraction of the time a whole case takes.

    ``test_fit`` leaves the middle of the back plate out, keeping a rim of
    that width around the outline and around every hole. Every dimension
    that can be wrong about a case -- the outside size, the corner radius,
    the clearance, the wall, the lip, and where the camera and the port are
    -- is still there to check, at about a third of the filament. The rim
    follows the holes for nothing, because the section is a distance field
    and that distance is measured to every surface, not just the outline.
    """
    path = CasePath(spec)
    lw = spec.line_width
    # The field is clamped at +-band, so the band has to reach past
    # everything measured against it -- including a test fit's rim, which is
    # a depth into the plate.
    band = max(4.0, spec.plate_perimeters * lw + 2.0, spec.wall,
               skirt_gap + (skirt + brim) * lw + 1.0, (test_fit or 0.0) + 1.0)
    fields: dict[tuple, Field] = {}
    last_slot = plan.palette.base

    for i, (z_top, h) in enumerate(spec.layer_zs()):
        if max_layers is not None and i >= max_layers:
            break
        z_mid = z_top - h / 2
        sec = section_at(spec, z_mid)
        key = sec.key()
        fld = fields.get(key)
        if fld is None:
            fld = fields[key] = Field(sec, spec.section_res, band=band)

        solid = z_mid < spec.back_thickness
        painted = i < spec.art_layers
        runs: list[Run] = []

        # Skirt and brim are contours at positive levels -- outside the part
        # is just the other side of the same field.
        if i == 0:
            for b in range(brim):
                for loop in fld.contours((b + 0.5) * lw):
                    runs.append(Run(loop, z_top, h, lw, "brim",
                                    plan.palette.base, True))
            for s in range(skirt):
                lvl = skirt_gap + brim * lw + (s + 0.5) * lw
                for loop in fld.contours(lvl):
                    runs.append(Run(loop, z_top, h, lw, "skirt",
                                    plan.palette.base, True))

        # Perimeters, innermost first so the outer one is laid against
        # solid material and keeps its surface. Each contour of the field
        # comes back as a loop per face of the wall, so a 1.7 mm wall at
        # 0.42 mm lines is two depths and four perimeters.
        depths = spec.plate_perimeters if solid else spec.wall_pairs
        width = lw if solid else spec.wall_line
        for k in range(depths - 1, -1, -1):
            level = -(k + 0.5) * width
            kind = "plate" if solid else ("wall-outer" if k == 0 else "wall")
            for loop in fld.contours(level):
                runs.append(Run(loop, z_top, h, width, kind,
                                plan.palette.base, True))

        if solid:
            # Solid infill, alternating direction so the plate does not warp
            # into a banana along one axis.
            level = -(spec.plate_perimeters * lw) + 0.15 * lw
            angle = 45.0 if i % 2 == 0 else 135.0
            floor = -test_fit if test_fit else None
            for line in fld.infill(level, lw, angle, floor=floor):
                runs.append(Run(line, z_top, h, lw, "infill",
                                plan.palette.base, False))

        # Colour. The skin is the only thing anyone sees, so it is the only
        # thing that costs a purge.
        #
        # Runs are built in the body colour rather than in slot 0 and fixed up
        # afterwards. The fix-up below still happens and the output is the
        # same either way, but a run that is never painted and never reaches
        # the fix-up -- one more kind, one early `continue` -- used to come
        # out in whatever filament slot 0 happened to hold.
        out: list[Run] = []
        for r in runs:
            paint_this = (painted and r.kind in ("plate", "infill")) or \
                         (wrap and r.kind == "wall-outer")
            if not paint_this:
                r.slot = plan.palette.base
                out.append(r)
                continue
            pts = r.pts + [r.pts[0]] if r.closed else r.pts
            for slot, piece in split(pts, plan):
                out.append(Run(piece, r.z, r.height, r.width, r.kind, slot,
                               False))

        layer = Layer(i, z_top, h, _order(out, last_slot))
        if layer.runs:
            last_slot = layer.runs[-1].slot
        path.layers.append(layer)
    return path


def _order(runs: list[Run], start_slot: int) -> list[Run]:
    """Group a layer's runs by colour, then chain each group for short travel.

    Starting on the slot the previous layer finished with saves one purge per
    layer, which over an eighty layer case is most of a spool of waste.
    """
    by_slot: dict[int, list[Run]] = {}
    for r in runs:
        by_slot.setdefault(r.slot, []).append(r)
    order = sorted(by_slot, key=lambda s: (s != start_slot, s))

    out: list[Run] = []
    here = (0.0, 0.0)
    for slot in order:
        group = by_slot[slot]
        # Keep skirt first and the outer perimeter after the inner ones;
        # within a kind, go to whatever is nearest.
        rank = {"skirt": 0, "brim": 1, "wall": 2, "plate": 2,
                "wall-outer": 3, "infill": 4}
        remaining = sorted(group, key=lambda r: rank.get(r.kind, 5))
        while remaining:
            tier = rank.get(remaining[0].kind, 5)
            batch = [r for r in remaining if rank.get(r.kind, 5) == tier]
            remaining = remaining[len(batch):]
            while batch:
                best = min(batch, key=lambda r: min(
                    math.dist(here, r.pts[0]), math.dist(here, r.pts[-1])))
                batch.remove(best)
                if (not best.closed
                        and math.dist(here, best.pts[-1])
                        < math.dist(here, best.pts[0])):
                    best.pts.reverse()
                out.append(best)
                here = best.pts[0] if best.closed else best.pts[-1]
    return out


# --------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------

def stats(spec: CaseSpec, path: CasePath, *, density: float = 1.24,
          filament_d: float = 1.75) -> dict:
    """Length and filament per slot, plus the things worth checking."""
    per_slot_mm3: dict[int, float] = {}
    length = 0.0
    points = 0
    for layer in path.layers:
        for r in layer.runs:
            if r.kind == "skirt":
                continue
            ln = r.length()
            length += ln
            points += len(r.pts)
            # Rectangle with semicircular ends, same as the lamp writer.
            w, hgt = max(r.width, r.height), min(r.width, r.height)
            area = (w - hgt) * hgt + math.pi * (hgt / 2) ** 2
            per_slot_mm3[r.slot] = per_slot_mm3.get(r.slot, 0.0) + ln * area
    fil_area = math.pi * (filament_d / 2) ** 2
    return {
        "layers": len(path.layers),
        "points": points,
        "path_length_m": length / 1000.0,
        "volume_mm3": sum(per_slot_mm3.values()),
        "grams": sum(per_slot_mm3.values()) * density / 1000.0,
        "per_slot_mm3": per_slot_mm3,
        "per_slot_g": {k: v * density / 1000.0 for k, v in per_slot_mm3.items()},
        "per_slot_m": {k: v / fil_area / 1000.0 for k, v in per_slot_mm3.items()},
        "tool_changes": path.tool_changes(),
        "height_mm": path.layers[-1].z if path.layers else 0.0,
    }
