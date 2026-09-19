"""Write the case out as multi-tool g-code, purge tower and all.

No slicer is involved, which means nothing downstream will build the purge
tower for us either. A tool change on an AMS or MMU leaves the old colour in
the melt zone, and if the next thing the nozzle does is draw on the back of
the case, the first centimetre of it is the previous colour. So the tower is
part of the writer, not an afterthought:

* Each change gets a dense strip of tower sized to ``purge_mm3`` at this
  layer's height. That is the volume being flushed, laid down somewhere that
  is not the case.
* Layers between the first and the last purge, but with no change of their
  own, get a sparse pass. Skipping them would leave the tower printing into
  a gap next time it is needed.
* Layers after the last purge get nothing. This is the difference between a
  tower that weighs more than the case and one that is two layers tall: a
  case whose artwork is all on the back plate changes colour for the first
  two layers and never again.

The tower is sized from the worst layer in the actual toolpath rather than
from a guess, and the writer reports what it cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .paint import PaintPlan
from .profiles import Filament, Printer
from .spec import CaseSpec
from .toolpath import CasePath, Layer, Run, stats


@dataclass
class Tower:
    """A purge tower, sized to the print that needs it."""

    x: float
    y: float
    w: float
    d: float
    #: Layer index -> how many dense purge strips that layer needs.
    purges: dict[int, int] = field(default_factory=dict)
    first: int = 0
    last: int = -1

    @property
    def active(self) -> bool:
        return self.last >= self.first and self.w > 0


def plan_tower(spec: CaseSpec, path: CasePath, filament: Filament, *,
               depth: float = 40.0, min_width: float = 12.0) -> Tower:
    """Work out where the tower goes and how big it has to be."""
    need = 0.0
    purges: dict[int, int] = {}
    # The start g-code selects the first tool, and there is nothing in the
    # nozzle yet to flush out, so that one is not a purge.
    current = next((r.slot for ly in path.layers for r in ly.runs), None)
    for layer in path.layers:
        changes = 0
        for slot in layer.slots:
            if slot != current:
                changes += 1
            current = slot
        if changes:
            purges[layer.index] = changes
            need = max(need, changes * filament.purge_mm3 / layer.height)
    if not purges:
        return Tower(0, 0, 0, 0)
    depth = min(depth, max(20.0, spec.outer_l * 0.4))
    width = max(min_width, math.ceil(need / depth))
    return Tower(0.0, 0.0, width, depth, purges,
                 min(purges), max(purges))


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------

def _speed(kind: str, f: Filament) -> float:
    return {"wall-outer": f.outer_speed, "wall": f.perimeter_speed,
            "plate": f.perimeter_speed, "infill": f.infill_speed,
            "skirt": f.outer_speed, "brim": f.outer_speed,
            "purge": f.purge_speed}.get(kind, f.perimeter_speed)


def write(spec: CaseSpec, path: CasePath, printer: Printer,
          filament: Filament, plan: PaintPlan, *, tower: Tower | None = None,
          origin: tuple[float, float] | None = None) -> str:
    """Render the toolpath as a g-code program."""
    if tower is None:
        tower = plan_tower(spec, path, filament)

    # Lay the case and the tower out side by side and centre the pair.
    gap = 6.0
    total_w = spec.outer_w + (gap + tower.w if tower.active else 0.0)
    if origin is None:
        cx = printer.bed_x / 2 - total_w / 2 + spec.outer_w / 2
        cy = printer.bed_y / 2
    else:
        cx, cy = origin
    tower.x = cx + spec.outer_w / 2 + gap + tower.w / 2
    tower.y = cy

    span_x = total_w + 2 * 4.0
    if span_x > printer.bed_x or spec.outer_l + 8 > printer.bed_y:
        raise ValueError(
            f"case plus a {tower.w:.0f} mm purge tower needs "
            f"{span_x:.0f} x {spec.outer_l + 8:.0f} mm and the "
            f"{printer.name} bed is {printer.bed_x:.0f} x {printer.bed_y:.0f}."
            " Lower --purge, or print it in fewer colours")

    st = stats(spec, path, density=filament.density,
               filament_d=printer.filament_diameter)
    fil_area = math.pi * (printer.filament_diameter / 2) ** 2

    out: list[str] = []
    w = out.append
    pal = plan.palette

    w("; parametric iPhone case, painted with the AMS")
    w(f"; generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    w(f"; {spec.phone.name} -- case {spec.outer_w:.1f} x {spec.outer_l:.1f} x "
      f"{spec.height:.1f} mm, {spec.clearance:.2f} mm clearance")
    w(f"; printer {printer.name} / filament {filament.name}")
    w(f"; {st['layers']} layers, {st['path_length_m']:.0f} m of extrusion, "
      f"~{st['grams']:.1f} g of part")
    for s in pal.slots:
        g = st["per_slot_g"].get(s.index, 0.0)
        w(f";   T{s.index} {s.name:<12} {s.hex}  {g:5.1f} g")
    w(f"; {st['tool_changes']} tool changes")
    if tower.active:
        w(f"; purge tower {tower.w:.0f} x {tower.d:.0f} mm at "
          f"({tower.x:.1f}, {tower.y:.1f}), layers {tower.first}-{tower.last}")
    else:
        w("; no purge tower (single colour)")
    w("; NOT SLICED -- written directly. Do not re-slice.")
    w("")

    fmt = dict(bed=filament.bed_temp, nozzle_temp=filament.nozzle_temp,
               bed_y_safe=printer.bed_y - 10.0,
               bed_x=printer.bed_x, bed_y=printer.bed_y,
               prime_x0=5.0, prime_x1=printer.bed_x - 5.0,
               prime_y=3.0, prime_y_2=6.0)
    first_tool = path.layers[0].runs[0].slot if path.layers and path.layers[0].runs \
        else pal.base
    w(printer.start_gcode.format(**fmt).rstrip())
    w(printer.tool_change.format(tool=first_tool))
    if printer.prime_gcode:
        w(printer.prime_gcode.format(**fmt).rstrip())
    w("G21 ; mm")
    w("G90 ; absolute positions")
    w("M82 ; absolute extrusion" if printer.absolute_e else "M83 ; relative")
    w("G92 E0")
    w("")

    state = _State(w, printer, filament, fil_area, cx, cy)
    state.tool = first_tool
    fan = -1

    for layer in path.layers:
        w("")
        w(";LAYER_CHANGE")
        w(f";Z:{layer.z:.3f}")
        want_fan = filament.fan_first_layer if layer.index == 0 else filament.fan
        if want_fan != fan:
            w(f"M106 S{round(want_fan * 255 / 100)}" if want_fan else "M107")
            fan = want_fan

        # Keep the tower level: anything the purges will not cover this
        # layer gets a sparse pass with whatever tool is already loaded.
        strips = tower.purges.get(layer.index, 0)
        if tower.active and tower.first <= layer.index <= tower.last:
            _tower_sparse(state, tower, layer, strips, filament)

        used = 0
        for run in layer.runs:
            if run.slot != state.tool:
                if tower.active:
                    _purge(state, tower, layer, used, strips, run.slot, filament)
                    used += 1
                else:
                    state.change_tool(run.slot)
            state.draw(run, _speed(run.kind, filament),
                       first_layer=layer.index == 0)

    w("")
    w(printer.end_gcode.format(**fmt).rstrip())
    w("")
    return "\n".join(out)


class _State:
    """Nozzle position, extruder counter and the moves that change them."""

    def __init__(self, w, printer, filament, fil_area, cx, cy):
        self.w = w
        self.printer = printer
        self.f = filament
        self.fil_area = fil_area
        self.cx, self.cy = cx, cy
        self.e = 0.0
        self.pos: tuple[float, float, float] | None = None
        self.tool = 0
        self.retracted = False
        self.feed = -1.0
        self.kind = ""

    # -- primitives ----------------------------------------------------

    def retract(self) -> None:
        if self.retracted or self.f.retract_mm <= 0:
            return
        self.e -= self.f.retract_mm
        self.w(f"G1 E{self.e:.4f} F{self.f.retract_speed}"
               if self.printer.absolute_e else
               f"G1 E-{self.f.retract_mm:.4f} F{self.f.retract_speed}")
        self.retracted = True

    def unretract(self) -> None:
        if not self.retracted:
            return
        self.e += self.f.retract_mm
        self.w(f"G1 E{self.e:.4f} F{self.f.retract_speed}"
               if self.printer.absolute_e else
               f"G1 E{self.f.retract_mm:.4f} F{self.f.retract_speed}")
        self.retracted = False

    def travel(self, x, y, z) -> None:
        """Retract, hop over whatever is in the way, and come back down."""
        fx, fy = x + self.cx, y + self.cy
        speed = self.f.travel_speed * 60
        if self.pos is None:
            self.w(f"G1 X{fx:.3f} Y{fy:.3f} F{speed:.0f}")
            self.w(f"G1 Z{z:.3f} F{speed:.0f}")
            self.pos = (fx, fy, z)
            self.feed = -1.0
            return
        d = math.dist(self.pos[:2], (fx, fy))
        if d < 1e-6 and abs(self.pos[2] - z) < 1e-6:
            return
        if d < self.f.retract_min and abs(self.pos[2] - z) < 1e-6:
            # Hopping and retracting across a 1 mm gap between two infill
            # lines costs more than it saves.
            self.w(f"G1 X{fx:.3f} Y{fy:.3f} F{speed:.0f}")
            self.pos = (fx, fy, z)
            self.feed = -1.0
            return
        self.retract()
        if self.f.z_hop > 0:
            self.w(f"G1 Z{max(self.pos[2], z) + self.f.z_hop:.3f} F{speed:.0f}")
        self.w(f"G1 X{fx:.3f} Y{fy:.3f} F{speed:.0f}")
        self.w(f"G1 Z{z:.3f} F{speed:.0f}")
        self.pos = (fx, fy, z)
        self.feed = -1.0

    def extrude_to(self, x, y, z, width, height, feed) -> None:
        fx, fy = x + self.cx, y + self.cy
        if self.pos is None:
            self.travel(x, y, z)
            return
        d = math.dist(self.pos[:2], (fx, fy))
        if d < 1e-9:
            return
        self.unretract()
        # Rectangle with semicircular ends, same model as the lamp writer.
        lw, lh = max(width, height), min(width, height)
        area = (lw - lh) * lh + math.pi * (lh / 2) ** 2
        self.e += d * area * self.f.flow / self.fil_area
        ecmd = (f" E{self.e:.4f}" if self.printer.absolute_e
                else f" E{d * area * self.f.flow / self.fil_area:.4f}")
        if abs(feed - self.feed) > 1:
            self.w(f"G1 X{fx:.3f} Y{fy:.3f}{ecmd} F{feed:.0f}")
            self.feed = feed
        else:
            self.w(f"G1 X{fx:.3f} Y{fy:.3f}{ecmd}")
        self.pos = (fx, fy, z)

    # -- higher level --------------------------------------------------

    def change_tool(self, slot: int) -> None:
        if slot == self.tool:
            return
        self.retract()
        if self.pos is not None:
            self.w(f"G1 Z{self.pos[2] + 2.0:.3f} "
                   f"F{self.f.travel_speed * 60:.0f}")
            self.pos = (self.pos[0], self.pos[1], self.pos[2] + 2.0)
        self.w(f"; colour change -> slot {slot}")
        self.w(self.printer.tool_change.format(tool=slot))
        self.tool = slot
        self.feed = -1.0

    def draw(self, run: Run, speed: float, *, first_layer: bool = False) -> None:
        pts = run.pts
        if len(pts) < 2:
            return
        if first_layer:
            speed = min(speed, self.f.first_layer_speed)
        if run.kind != self.kind:
            self.w(f";TYPE:{run.kind}")
            self.kind = run.kind
        self.travel(pts[0][0], pts[0][1], run.z)
        for x, y in pts[1:]:
            self.extrude_to(x, y, run.z, run.width, run.height, speed * 60)
        if run.closed:
            self.extrude_to(pts[0][0], pts[0][1], run.z, run.width,
                            run.height, speed * 60)


# --------------------------------------------------------------------------
# the tower itself
# --------------------------------------------------------------------------

def _serpentine(x0, x1, y0, y1, spacing) -> list[tuple[float, float]]:
    """Fill a rectangle with one continuous back-and-forth path."""
    pts: list[tuple[float, float]] = []
    n = max(1, int((x1 - x0) / spacing))
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n if n else x0
        if i % 2 == 0:
            pts += [(x, y0), (x, y1)]
        else:
            pts += [(x, y1), (x, y0)]
    return pts


def _purge(state: _State, tower: Tower, layer: Layer, index: int, count: int,
           slot: int, f: Filament) -> None:
    """Swap tools over the tower and flush the old colour into it."""
    need_w = tower.w / max(1, count)
    x0 = tower.x - tower.w / 2 + index * need_w
    x1 = min(x0 + need_w, tower.x + tower.w / 2)
    y0, y1 = tower.y - tower.d / 2, tower.y + tower.d / 2
    state.change_tool(slot)
    state.w(";TYPE:purge")
    state.kind = "purge"
    pts = _serpentine(x0 - state.cx, x1 - state.cx,
                      y0 - state.cy, y1 - state.cy, _purge_line(state))
    state.travel(pts[0][0], pts[0][1], layer.z)
    for x, y in pts[1:]:
        state.extrude_to(x, y, layer.z, _purge_line(state), layer.height,
                         f.purge_speed * 60)


def _tower_sparse(state: _State, tower: Tower, layer: Layer, strips: int,
                  f: Filament) -> None:
    """Keep the tower climbing on a layer that has nothing to purge.

    Only the part of the footprint the purges will not reach, and at three
    times the line spacing: it exists to hold the next dense layer up, not
    to be strong.
    """
    need_w = tower.w / max(1, strips) if strips else 0.0
    x0 = tower.x - tower.w / 2 + strips * need_w
    x1 = tower.x + tower.w / 2
    if x1 - x0 < _purge_line(state):
        return
    y0, y1 = tower.y - tower.d / 2, tower.y + tower.d / 2
    state.w(";TYPE:tower-sparse")
    state.kind = "tower-sparse"
    pts = _serpentine(x0 - state.cx, x1 - state.cx, y0 - state.cy,
                      y1 - state.cy, _purge_line(state) * 3)
    state.travel(pts[0][0], pts[0][1], layer.z)
    for x, y in pts[1:]:
        state.extrude_to(x, y, layer.z, _purge_line(state), layer.height,
                         f.purge_speed * 60)


def _purge_line(state: _State) -> float:
    """Extrusion width of a tower line. Wide and fast: it is being binned."""
    return state.printer.nozzle * 1.05


def tower_stats(spec: CaseSpec, path: CasePath, tower: Tower,
                printer: Printer, filament: Filament) -> dict:
    """What the tower costs, which is the number people want before printing."""
    if not tower.active:
        return {"grams": 0.0, "layers": 0}
    spacing = printer.nozzle * 1.05
    vol = 0.0
    layers = 0
    for layer in path.layers:
        if not (tower.first <= layer.index <= tower.last):
            continue
        layers += 1
        strips = tower.purges.get(layer.index, 0)
        dense_w = tower.w if strips else 0.0
        sparse_w = tower.w - dense_w
        vol += (dense_w * tower.d * layer.height
                + sparse_w * tower.d * layer.height / 3.0)
    return {"grams": vol * filament.density / 1000.0, "layers": layers,
            "volume_mm3": vol}
