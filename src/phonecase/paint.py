"""Turning artwork into AMS slot assignments.

The whole colour question is answered once, up front, by rasterising the
artwork into a grid of slot numbers over the case footprint. Everything
afterwards -- which colour a perimeter is, where along an infill line the
colour changes, how many grams of each filament this will take -- is a
lookup in that grid.

The alternative, testing each toolpath point against the polygons directly,
is the obvious way and it is far too slow: a back plate is tens of thousands
of samples against hundreds of edges. Rasterising is one scanline pass per
shape and an O(1) lookup forever after. At 0.15 mm the grid is a third of a
line width, so the colour boundaries it produces land inside the bead that
covers them.

The mirror lives here too, and only here. The case prints back-face-down, so
the artwork goes into the g-code flipped in x; get that wrong and everything
reads backwards on the finished case with no way to tell until it is off the
plate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .svgart import Art, Shape

UNPAINTED = 255


@dataclass(frozen=True)
class Slot:
    """One AMS slot: a filament of a given colour in a given position."""

    index: int
    name: str
    rgb: tuple[int, int, int]

    @property
    def hex(self) -> str:
        return "#%02x%02x%02x" % self.rgb


@dataclass
class Palette:
    """What is loaded in the AMS, and which slot is the case's body colour."""

    slots: list[Slot]
    base: int = 0

    def __post_init__(self) -> None:
        if not self.slots:
            raise ValueError("a palette needs at least one slot")
        if not 0 <= self.base < len(self.slots):
            raise ValueError(f"base slot {self.base} is not loaded")

    def __len__(self) -> int:
        return len(self.slots)

    def match(self, rgb: tuple[int, int, int]) -> int:
        """Nearest loaded filament to an arbitrary colour.

        Redmean rather than plain RGB distance: plain RGB happily decides
        that a saturated red is closer to a saturated blue than to a dark
        red, which is exactly the swap you notice on a finished case.
        """
        best, best_d = self.base, None
        for s in self.slots:
            rm = (s.rgb[0] + rgb[0]) / 2
            dr, dg, db = (s.rgb[0] - rgb[0], s.rgb[1] - rgb[1], s.rgb[2] - rgb[2])
            d = ((2 + rm / 256) * dr * dr + 4 * dg * dg
                 + (2 + (255 - rm) / 256) * db * db)
            if best_d is None or d < best_d:
                best, best_d = s.index, d
        return best

    @classmethod
    def parse(cls, entries: list[str], base: int = 0) -> "Palette":
        """Build from ``2=#e4572e:coral`` style command line entries."""
        slots: dict[int, Slot] = {}
        for i, raw in enumerate(entries):
            spec = raw
            idx = i
            if "=" in raw and raw.split("=", 1)[0].strip().isdigit():
                head, spec = raw.split("=", 1)
                idx = int(head)
            colour, _, name = spec.partition(":")
            rgb = _hex(colour.strip())
            if rgb is None:
                raise ValueError(f"{raw!r}: {colour!r} is not a #rrggbb colour")
            if idx in slots:
                raise ValueError(f"slot {idx} given twice")
            slots[idx] = Slot(idx, name.strip() or colour.strip(), rgb)
        if not slots:
            raise ValueError("no slots given")
        order = sorted(slots)
        if order != list(range(len(order))):
            raise ValueError(
                f"slots must be numbered 0..n with no gaps, got {order}")
        return cls([slots[i] for i in order], base)


def _hex(s: str) -> tuple[int, int, int] | None:
    from .svgart import _parse_rgb
    return _parse_rgb(s)


# --------------------------------------------------------------------------
# placing the artwork on the case
# --------------------------------------------------------------------------

@dataclass
class Placement:
    """How SVG user space maps onto the back of the case.

    ``dx`` and ``dy`` are in the frame you look at the finished case in, not
    the frame the g-code is written in. Positive ``dx`` moves the artwork to
    the *right as you hold it*, which is the case's -x, because the case
    prints face down and everything on that face is mirrored. Anything else
    is a control that pushes the opposite way from the picture above it.
    """

    scale_x: float
    scale_y: float
    rotate_deg: float
    dx: float
    dy: float
    mirror: bool = True
    src_centre: tuple[float, float] = (0.0, 0.0)

    def apply(self, p: tuple[float, float]) -> tuple[float, float]:
        x = (p[0] - self.src_centre[0]) * self.scale_x
        # SVG y runs down the page and the case's y runs up the phone.
        y = -(p[1] - self.src_centre[1]) * self.scale_y
        if self.rotate_deg:
            a = math.radians(self.rotate_deg)
            c, s = math.cos(a), math.sin(a)
            x, y = x * c - y * s, x * s + y * c
        if self.mirror:
            x = -x
        # -dx, because +x on the case points left in the view of it. +y needs
        # no such correction: the top of the phone is the top of the view.
        return (x - self.dx, y + self.dy)


def place(art: Art, width: float, length: float, *, fit: str = "contain",
          margin: float = 2.0, scale: float = 1.0, rotate: float = 0.0,
          offset: tuple[float, float] = (0.0, 0.0), mirror: bool = True,
          box: str = "content") -> Placement:
    """Work out the transform that drops the artwork onto the back face.

    ``fit`` is ``contain`` (all of it, letterboxed), ``cover`` (fills the
    back, cropped), ``stretch`` (distorted to fit) or ``none`` (user units
    are millimetres).
    """
    x0, y0, x1, y1 = art.bbox() if box == "content" else art.view
    sw, sh = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    # Rotating the artwork changes the box it has to fit into.
    a = abs(math.radians(rotate))
    eff_w = sw * abs(math.cos(a)) + sh * abs(math.sin(a))
    eff_h = sw * abs(math.sin(a)) + sh * abs(math.cos(a))
    dw, dh = max(width - 2 * margin, 1.0), max(length - 2 * margin, 1.0)

    if fit == "none":
        sx = sy = 1.0
    elif fit == "stretch":
        sx, sy = dw / eff_w, dh / eff_h
    elif fit == "cover":
        sx = sy = max(dw / eff_w, dh / eff_h)
    else:
        sx = sy = min(dw / eff_w, dh / eff_h)
    return Placement(sx * scale, sy * scale, rotate, offset[0], offset[1],
                     mirror, ((x0 + x1) / 2, (y0 + y1) / 2))


# --------------------------------------------------------------------------
# the raster
# --------------------------------------------------------------------------

class Raster:
    """Slot number per grid cell over the case footprint."""

    def __init__(self, width: float, length: float, res: float, base: int):
        self.res = res
        self.x0 = -width / 2
        self.y0 = -length / 2
        self.nx = int(math.ceil(width / res)) + 1
        self.ny = int(math.ceil(length / res)) + 1
        self.base = base
        self.data = bytearray([UNPAINTED]) * (self.nx * self.ny)

    def slot_at(self, x: float, y: float) -> int:
        ix = int((x - self.x0) / self.res)
        iy = int((y - self.y0) / self.res)
        if ix < 0 or iy < 0 or ix >= self.nx or iy >= self.ny:
            return self.base
        v = self.data[iy * self.nx + ix]
        return self.base if v == UNPAINTED else v

    def area_mm2(self) -> dict[int, float]:
        """Painted area per slot, including the base showing through."""
        cell = self.res * self.res
        counts: dict[int, int] = {}
        for v in self.data:
            counts[v] = counts.get(v, 0) + 1
        out: dict[int, float] = {}
        for v, n in counts.items():
            slot = self.base if v == UNPAINTED else v
            out[slot] = out.get(slot, 0.0) + n * cell
        return out

    def used_slots(self) -> set[int]:
        return {self.base if v == UNPAINTED else v for v in set(self.data)}

    # -- rasterising ---------------------------------------------------

    def draw(self, shape: Shape, placement: Placement, slot: int) -> None:
        """Scanline-fill one shape, overwriting whatever was under it."""
        polys = [[placement.apply(p) for p in sp] for sp in shape.subpaths
                 if len(sp) >= 3]
        if not polys:
            return
        # Active edge table, bucketed by the first row each edge touches, so
        # the cost is edges plus rows rather than edges times rows.
        buckets: dict[int, list[tuple[float, float, float, int]]] = {}
        y_lo, y_hi = self.ny, -1
        for poly in polys:
            pts = poly if math.dist(poly[0], poly[-1]) < 1e-12 else poly + [poly[0]]
            for i in range(len(pts) - 1):
                (ax, ay), (bx, by) = pts[i], pts[i + 1]
                if ay == by:
                    continue
                direction = 1 if by > ay else -1
                if direction < 0:
                    (ax, ay), (bx, by) = (bx, by), (ax, ay)
                r0 = int(math.ceil((ay - self.y0) / self.res - 0.5))
                r1 = int(math.ceil((by - self.y0) / self.res - 0.5))
                r0, r1 = max(0, r0), min(self.ny, r1)
                if r0 >= r1:
                    continue
                slope = (bx - ax) / (by - ay)
                buckets.setdefault(r0, []).append((by, ax, ay, slope, direction))
                y_lo, y_hi = min(y_lo, r0), max(y_hi, r1)

        active: list[tuple] = []
        for row in range(max(0, y_lo), min(self.ny, y_hi + 1)):
            yc = self.y0 + (row + 0.5) * self.res
            if row in buckets:
                active += buckets[row]
            if not active:
                continue
            active = [e for e in active if e[0] > yc]
            xs = sorted(((e[1] + (yc - e[2]) * e[3], e[4]) for e in active),
                        key=lambda t: t[0])
            spans = _spans(xs, shape.even_odd)
            base = row * self.nx
            for xa, xb in spans:
                ia = max(0, int(math.ceil((xa - self.x0) / self.res - 0.5)))
                ib = min(self.nx, int(math.ceil((xb - self.x0) / self.res - 0.5)))
                if ib > ia:
                    self.data[base + ia:base + ib] = bytes([slot]) * (ib - ia)


def _spans(xs, even_odd: bool) -> list[tuple[float, float]]:
    out = []
    if even_odd:
        for i in range(0, len(xs) - 1, 2):
            out.append((xs[i][0], xs[i + 1][0]))
    else:
        wind = 0
        start = 0.0
        for x, d in xs:
            if wind == 0:
                start = x
            wind += d
            if wind == 0:
                out.append((start, x))
    return out


@dataclass
class PaintPlan:
    """A finished colour plan: the raster, plus what went into it."""

    raster: Raster
    palette: Palette
    placement: Placement
    #: The artwork the raster was made from, kept so anything that needs the
    #: shapes themselves rather than the grid -- the 3MF, which carries the
    #: colours as real inlays -- does not have to be handed it separately.
    art: Art | None = None
    #: Each distinct SVG colour, the slot it became, and its share of the art.
    mapping: list[tuple[tuple[int, int, int], int, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def slot_at(self, x: float, y: float) -> int:
        return self.raster.slot_at(x, y)


def plan(art: Art | None, palette: Palette, width: float, length: float, *,
         res: float = 0.15, **place_kw) -> PaintPlan:
    """Rasterise the artwork into slot numbers over the case footprint."""
    pl = place(art, width, length, **place_kw) if art else Placement(
        1, 1, 0, 0, 0, False)
    raster = Raster(width, length, res, palette.base)
    warnings: list[str] = []
    mapping: list[tuple[tuple[int, int, int], int, float]] = []

    if art is not None:
        warnings += art.warnings
        total = sum(a for _, a in art.colours()) or 1.0
        for rgb, area in art.colours():
            mapping.append((rgb, palette.match(rgb), area / total))
        # Document order: later shapes cover earlier ones, same as a viewer.
        for shape in art.shapes:
            raster.draw(shape, pl, palette.match(shape.rgb))

        off = _fraction_off_the_case(art, pl, width, length)
        if off > 0.02:
            warnings.append(
                f"{off * 100:.0f}% of the artwork falls outside the case and "
                "will not be printed; move it back or scale it down")

        collapsed: dict[int, list[tuple[int, int, int]]] = {}
        for rgb, slot, _ in mapping:
            collapsed.setdefault(slot, []).append(rgb)
        for slot, rgbs in collapsed.items():
            if len(rgbs) > 1:
                warnings.append(
                    f"{len(rgbs)} artwork colours all land on slot {slot} "
                    f"({palette.slots[slot].name}); they will merge")
    return PaintPlan(raster, palette, pl, art, mapping, warnings)


def _fraction_off_the_case(art: Art, pl: Placement,
                           width: float, length: float) -> float:
    """How much of the placed artwork misses the case, by area.

    Worth saying out loud: nothing stops you moving a drawing off the edge,
    and what falls off does not come back as an error -- it is simply not in
    the g-code, and you find out when the case comes off the plate with half
    a logo on it.
    """
    x0, y0, x1, y1 = art.bbox()
    corners = [pl.apply(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    ax0 = min(c[0] for c in corners)
    ax1 = max(c[0] for c in corners)
    ay0 = min(c[1] for c in corners)
    ay1 = max(c[1] for c in corners)
    placed = (ax1 - ax0) * (ay1 - ay0)
    if placed <= 0:
        return 0.0
    ox = max(0.0, min(ax1, width / 2) - max(ax0, -width / 2))
    oy = max(0.0, min(ay1, length / 2) - max(ay0, -length / 2))
    return max(0.0, 1.0 - (ox * oy) / placed)


# --------------------------------------------------------------------------
# splitting a toolpath by colour
# --------------------------------------------------------------------------

def split(pts: list[tuple[float, float]], plan: PaintPlan, *,
          step: float = 0.35, refine: int = 6
          ) -> list[tuple[int, list[tuple[float, float]]]]:
    """Cut a polyline where the colour under it changes.

    The crossing is bisected rather than snapped to the nearest sample, so a
    straight edge in the artwork comes out straight in the g-code instead of
    stepping by the sample spacing.
    """
    if len(pts) < 2:
        return [(plan.slot_at(*pts[0]), list(pts))] if pts else []

    out: list[tuple[int, list[tuple[float, float]]]] = []
    cur_slot = plan.slot_at(*pts[0])
    run = [pts[0]]
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        d = math.dist(a, b)
        n = max(1, int(math.ceil(d / step)))
        for k in range(1, n + 1):
            t = k / n
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            s = plan.slot_at(*p)
            if s == cur_slot:
                if k == n:
                    run.append(p)
                continue
            prev = run[-1]
            lo, hi = 0.0, 1.0
            for _ in range(refine):
                mid = (lo + hi) / 2
                q = (prev[0] + (p[0] - prev[0]) * mid,
                     prev[1] + (p[1] - prev[1]) * mid)
                if plan.slot_at(*q) == cur_slot:
                    lo = mid
                else:
                    hi = mid
            cut = (prev[0] + (p[0] - prev[0]) * hi,
                   prev[1] + (p[1] - prev[1]) * hi)
            run.append(cut)
            if len(run) >= 2:
                out.append((cur_slot, run))
            cur_slot = s
            run = [cut, p]
    if len(run) >= 2:
        out.append((cur_slot, run))
    return out
