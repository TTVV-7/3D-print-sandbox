"""The little slicer: a cross-section, as a distance field, traced into loops.

A phone case is a thin shell with holes punched through it, and the holes are
the hard part. The obvious way to build the perimeters -- take the outline,
offset it inwards a few times, then cut out the bits that fall inside a hole
-- leaves every loop severed at the hole edge, with the cut ends of four lines
staring out of it. That is not what a hole in a case looks like. The
perimeters are supposed to *turn* and run around the opening.

So the section is not drawn, it is **solved**. Each cross-section is a signed
distance function::

    d(x, y) = max( outer, -cavity, -hole_0, -hole_1, ... )

negative inside the plastic, and every perimeter is just an isocontour of it:
loop ``i`` is the set of points at ``d = -(i + 0.5) * line_width``. Offsetting,
routing around holes, merging two perimeters where the wall narrows and
splitting them again -- all of it falls out of the contour rather than being
special-cased, because the distance field already knows.

The contours come from marching squares over a grid, which is the slow part
and the reason :class:`Field` is cached per distinct section rather than per
layer. A case has maybe twenty distinct sections and eighty layers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


Point = tuple[float, float]
Loop = list[Point]


@dataclass(frozen=True)
class RRect:
    """A rounded rectangle, as an exact signed distance function."""

    cx: float
    cy: float
    hx: float          # half width
    hy: float          # half height
    r: float = 0.0

    def sdf(self, x: float, y: float) -> float:
        r = min(self.r, self.hx, self.hy)
        qx = abs(x - self.cx) - (self.hx - r)
        qy = abs(y - self.cy) - (self.hy - r)
        if qx > 0.0 and qy > 0.0:
            return math.hypot(qx, qy) - r
        return max(qx, qy) - r

    def bbox(self, pad: float = 0.0) -> tuple[float, float, float, float]:
        return (self.cx - self.hx - pad, self.cy - self.hy - pad,
                self.cx + self.hx + pad, self.cy + self.hy + pad)


@dataclass
class Section:
    """One horizontal slice of the case: an outline, less a cavity and holes."""

    outer: RRect
    cavity: RRect | None = None
    holes: tuple[RRect, ...] = ()

    def sdf(self, x: float, y: float) -> float:
        d = self.outer.sdf(x, y)
        if self.cavity is not None:
            d = max(d, -self.cavity.sdf(x, y))
        for h in self.holes:
            d = max(d, -h.sdf(x, y))
        return d

    def key(self) -> tuple:
        """Identity for caching. Sections repeat for layer after layer."""
        def q(rr: RRect | None):
            if rr is None:
                return None
            return tuple(round(v, 4) for v in (rr.cx, rr.cy, rr.hx, rr.hy, rr.r))
        return (q(self.outer), q(self.cavity), tuple(q(h) for h in self.holes))


# --------------------------------------------------------------------------
# distance field
# --------------------------------------------------------------------------

#: How the twelve unambiguous marching-squares cases connect cell edges, with
#: the inside of the contour always on the left of travel. Edge 0 is the
#: bottom of the cell, then right, top, left. Cases 5 and 10 are the saddles
#: and are resolved at run time against the cell centre.
_MS: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((0, 3),), 2: ((1, 0),), 3: ((1, 3),), 4: ((2, 1),),
    6: ((2, 0),), 7: ((2, 3),), 8: ((3, 2),), 9: ((0, 2),),
    11: ((1, 2),), 12: ((3, 1),), 13: ((0, 1),), 14: ((3, 0),),
}


class Field:
    """A sampled signed distance field, and the contours you can pull from it."""

    def __init__(self, section: Section, res: float, pad: float = 1.5,
                 *, band: float = 4.0):
        x0, y0, x1, y1 = section.outer.bbox(pad)
        self.res = res
        self.x0, self.y0 = x0, y0
        self.nx = int(math.ceil((x1 - x0) / res)) + 1
        self.ny = int(math.ceil((y1 - y0) / res)) + 1
        self.section = section
        self.band = band

        # Values are clamped to +-band. Nothing is traced or filled that far
        # from a surface, so clamping costs nothing and buys two things: a
        # shape more than a band outside its own bounding box cannot win the
        # max() and is skipped entirely, and whole runs of clamped cells can
        # later be skipped by the contour tracer. Most of a back plate is
        # nowhere near a hole, and this is most of the runtime of the
        # generator.
        subtract = []
        if section.cavity is not None:
            subtract.append((section.cavity, section.cavity.bbox(band)))
        for h in section.holes:
            subtract.append((h, h.bbox(band)))

        o = section.outer
        orx = min(o.r, o.hx, o.hy)
        # The outer distance splits into a per-column and a per-row term, so
        # the column term is computed once for the whole grid.
        axs = [abs(x0 + ix * res - o.cx) - (o.hx - orx) for ix in range(self.nx)]

        v: list[float] = []
        spans: list[list[tuple[int, int]]] = []
        ap = v.append
        for iy in range(self.ny):
            y = y0 + iy * res
            qy = abs(y - o.cy) - (o.hy - orx)
            row_spans: list[tuple[int, int]] = []
            run_start = -1
            for ix in range(self.nx):
                qx = axs[ix]
                if qx > 0.0 and qy > 0.0:
                    d = math.hypot(qx, qy) - orx
                elif qx > qy:
                    d = qx - orx
                else:
                    d = qy - orx
                if d > band:
                    d = band
                elif d < -band:
                    d = -band
                if subtract:
                    x = x0 + ix * res
                    for shape, (bx0, by0, bx1, by1) in subtract:
                        if bx0 <= x <= bx1 and by0 <= y <= by1:
                            s = -shape.sdf(x, y)
                            if s > d:
                                d = band if s > band else s
                ap(d)
                if -band < d < band:
                    if run_start < 0:
                        run_start = ix
                elif run_start >= 0:
                    row_spans.append((run_start, ix))
                    run_start = -1
            if run_start >= 0:
                row_spans.append((run_start, self.nx))
            spans.append(row_spans)
        self.v = v
        self.spans = spans

    # -- sampling ------------------------------------------------------

    def at(self, x: float, y: float) -> float:
        """Bilinear sample. Outside the grid reads as solidly outside."""
        gx = (x - self.x0) / self.res
        gy = (y - self.y0) / self.res
        ix, iy = int(math.floor(gx)), int(math.floor(gy))
        if ix < 0 or iy < 0 or ix >= self.nx - 1 or iy >= self.ny - 1:
            return 1e3
        fx, fy = gx - ix, gy - iy
        row = iy * self.nx + ix
        v00 = self.v[row]
        v10 = self.v[row + 1]
        v01 = self.v[row + self.nx]
        v11 = self.v[row + self.nx + 1]
        return ((v00 * (1 - fx) + v10 * fx) * (1 - fy)
                + (v01 * (1 - fx) + v11 * fx) * fy)

    def inside(self, x: float, y: float, level: float = 0.0) -> bool:
        return self.at(x, y) <= level

    # -- contours ------------------------------------------------------

    def contours(self, level: float, *, simplify: float = 0.02) -> list[Loop]:
        """Trace the closed loops of ``d == level`` out of the grid."""
        nx, ny, v, res = self.nx, self.ny, self.v, self.res
        x0, y0 = self.x0, self.y0

        # Each crossing sits on a unique grid edge, so loops are chained by
        # edge identity rather than by comparing floating-point endpoints.
        pos: dict[tuple[int, int, int], Point] = {}
        link: dict[tuple[int, int, int], tuple[int, int, int]] = {}

        def hkey(ix, iy):
            return (0, ix, iy)

        def vkey(ix, iy):
            return (1, ix, iy)

        def place(key, ax, ay, bx, by, va, vb):
            if key not in pos:
                t = 0.5 if vb == va else (level - va) / (vb - va)
                t = min(1.0, max(0.0, t))
                pos[key] = (ax + (bx - ax) * t, ay + (by - ay) * t)
            return key

        for iy in range(ny - 1):
            base = iy * nx
            ay = y0 + iy * res
            by = ay + res
            # Only a cell with an unclamped corner can hold a crossing, and
            # those come in a handful of column runs per row.
            for ca, cb in _merge(self.spans[iy], self.spans[iy + 1], nx - 1):
                for ix in range(ca, cb):
                    i00 = base + ix
                    v00, v10 = v[i00], v[i00 + 1]
                    v01, v11 = v[i00 + nx], v[i00 + nx + 1]
                    idx = ((1 if v00 < level else 0) | (2 if v10 < level else 0)
                           | (4 if v11 < level else 0) | (8 if v01 < level else 0))
                    if idx == 0 or idx == 15:
                        continue
                    ax = x0 + ix * res
                    bx = ax + res

                    def edge(e, ix=ix, iy=iy, ax=ax, ay=ay, bx=bx, by=by,
                             v00=v00, v10=v10, v01=v01, v11=v11):
                        if e == 0:
                            return place(hkey(ix, iy), ax, ay, bx, ay, v00, v10)
                        if e == 1:
                            return place(vkey(ix + 1, iy), bx, ay, bx, by, v10, v11)
                        if e == 2:
                            return place(hkey(ix, iy + 1), ax, by, bx, by, v01, v11)
                        return place(vkey(ix, iy), ax, ay, ax, by, v00, v01)

                    if idx in (5, 10):
                        # A saddle: the cell holds two separate pieces of
                        # contour and which pairs up with which depends on
                        # whether the middle of the cell is inside.
                        centre = (v00 + v10 + v01 + v11) / 4.0
                        inside_centre = centre < level
                        if idx == 5:
                            pairs = (((0, 1), (2, 3)) if inside_centre
                                     else ((0, 3), (2, 1)))
                        else:
                            pairs = (((3, 0), (1, 2)) if inside_centre
                                     else ((1, 0), (3, 2)))
                    else:
                        pairs = _MS[idx]
                    for a, b in pairs:
                        link[edge(a)] = edge(b)

        loops: list[Loop] = []
        while link:
            start = next(iter(link))
            loop: Loop = []
            k = start
            while k in link:
                loop.append(pos[k])
                nxt = link.pop(k)
                k = nxt
                if k == start:
                    break
            if len(loop) >= 4:
                loops.append(_simplify(loop, simplify))
        return loops

    # -- infill --------------------------------------------------------

    def infill(self, level: float, spacing: float, angle_deg: float,
               *, step: float | None = None,
               floor: float | None = None) -> list[list[Point]]:
        """Straight lines at ``angle_deg``, clipped to ``d <= level``.

        With ``floor`` set, also clipped to ``d >= floor``, which fills a
        band around the boundary rather than the whole region. Because ``d``
        is the distance to *any* surface, that band follows the edges of the
        holes as well as the outline, for free.

        Sampled along each line rather than intersected analytically, because
        the region is a distance field and not a polygon. The ends are then
        walked back onto the boundary by bisection, so the infill meets the
        perimeter instead of stopping a sample short of it.
        """
        if step is None:
            step = spacing * 0.5
        a = math.radians(angle_deg)
        ca, sa = math.cos(a), math.sin(a)
        x0, y0 = self.x0, self.y0
        x1 = x0 + (self.nx - 1) * self.res
        y1 = y0 + (self.ny - 1) * self.res
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        us = [p[0] * ca + p[1] * sa for p in corners]
        vs = [-p[0] * sa + p[1] * ca for p in corners]

        out: list[list[Point]] = []
        n = int((max(vs) - min(vs)) / spacing) + 1
        for i in range(n + 1):
            vv = min(vs) + i * spacing
            u = min(us)
            u_end = max(us)
            run: list[Point] = []
            while u <= u_end:
                p = (u * ca - vv * sa, u * sa + vv * ca)
                d = self.at(*p)
                if d <= level and (floor is None or d >= floor):
                    run.append(p)
                elif run:
                    out.append(self._trim(run, vv, ca, sa, level, step,
                                          floor))
                    run = []
                u += step
            if run:
                out.append(self._trim(run, vv, ca, sa, level, step, floor))
        return [r for r in out if _length(r) > spacing * 0.6]

    def _trim(self, run, vv, ca, sa, level, step, floor=None) -> list[Point]:
        """Push a sampled run's two ends out to the true boundary."""
        def ok(u):
            d = self.at(u * ca - vv * sa, u * sa + vv * ca)
            return d <= level and (floor is None or d >= floor)

        def refine(inside_u, outside_u):
            for _ in range(10):
                mid = (inside_u + outside_u) / 2
                if ok(mid):
                    inside_u = mid
                else:
                    outside_u = mid
            return inside_u

        u_lo = run[0][0] * ca + run[0][1] * sa
        u_hi = run[-1][0] * ca + run[-1][1] * sa
        lo = refine(u_lo, u_lo - step)
        hi = refine(u_hi, u_hi + step)
        return [(lo * ca - vv * sa, lo * sa + vv * ca),
                (hi * ca - vv * sa, hi * sa + vv * ca)]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _merge(a: list[tuple[int, int]], b: list[tuple[int, int]],
           limit: int) -> list[tuple[int, int]]:
    """Union two lists of column runs, grown by one cell and clipped."""
    if not a and not b:
        return []
    runs = sorted(a + b)
    out: list[tuple[int, int]] = []
    for lo, hi in runs:
        lo, hi = max(0, lo - 1), min(limit, hi + 1)
        if lo >= hi:
            continue
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def _length(pts: list[Point]) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _simplify(pts: Loop, tol: float) -> Loop:
    """Drop points that sit on the line between their neighbours.

    Marching squares emits one point per crossed cell, which is far more than
    a straight wall needs. Collinear thinning cuts a case's g-code roughly in
    half and changes the path not at all.
    """
    if tol <= 0 or len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = out[-1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        # Perpendicular distance of b from the segment a->c.
        ux, uy = cx - ax, cy - ay
        n = math.hypot(ux, uy)
        if n < 1e-12:
            continue
        if abs((bx - ax) * uy - (by - ay) * ux) / n > tol:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def resample(pts: list[Point], step: float) -> list[Point]:
    """Insert points so no gap exceeds ``step``. Used before colour splitting."""
    if len(pts) < 2:
        return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts)):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        d = math.hypot(bx - ax, by - ay)
        n = int(d / step)
        for k in range(1, n + 1):
            t = k * step / d
            if t < 1.0:
                out.append((ax + (bx - ax) * t, ay + (by - ay) * t))
        out.append((bx, by))
    return out
