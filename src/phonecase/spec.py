"""What a phone is, what a case for it has to be, and what would ruin it.

Coordinate frame, used everywhere in this package:

* ``x`` across the phone, ``y`` along it, ``z`` up from the outer back face.
* The origin is the centre of the back face.
* ``x`` and ``y`` are **as you see the phone from the front** -- +x is the
  side the power button is on, +y is the top. The camera therefore sits at
  positive x and positive y, because it is on the phone's back and the frame
  does not flip when you turn the phone over.

The case prints back-face-down, so ``z`` in this frame is ``z`` on the bed and
the artwork lands on layer 1 against the glass. That is the good news. The
catch is that layer 1 is the face you *cannot see while it prints*: what you
draw has to go into the g-code mirrored, or the finished case reads backwards.
:mod:`phonecase.paint` does that mirror, once, and nothing else may.

A NOTE ON THE NUMBERS BELOW, which matters more than any of the code.

The body dimensions are published spec-sheet figures. The camera openings and
the button positions are **not** published; they are measured-by-eye estimates
and they are the numbers most likely to be wrong for your phone. Every one of
them is overridable from the command line, and ``--test-fit`` exists so that
finding out costs twenty minutes instead of six hours. Print that first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Cutout:
    """A hole in one face of the case.

    ``face`` is ``"back"`` or one of ``"top" / "bottom" / "left" / "right"``
    (the phone's own top, bottom, left and right, seen from the front).

    For a back cutout, ``(u, v)`` is its centre in ``(x, y)`` and the hole goes
    straight through the back plate. For a side cutout, ``u`` runs along the
    face -- x for top/bottom, y for left/right -- and ``v`` is the centre
    height above the outer back face, so the hole is a rounded rectangle in
    the unrolled ``(u, z)`` plane and pierces the wall.
    """

    name: str
    face: str
    u: float
    v: float
    w: float
    h: float
    r: float = 2.0

    def __post_init__(self) -> None:
        if self.face not in ("back", "top", "bottom", "left", "right"):
            raise ValueError(f"{self.name}: unknown face {self.face!r}")
        if min(self.w, self.h) <= 0:
            raise ValueError(f"{self.name}: cutout has no size")
        if self.r > min(self.w, self.h) / 2 + 1e-9:
            raise ValueError(
                f"{self.name}: corner radius {self.r} does not fit in "
                f"{self.w} x {self.h}")

    @property
    def flat_top_span(self) -> float:
        """Width of the unsupported bridge over the hole (mm)."""
        return max(0.0, self.w - 2 * self.r)


@dataclass(frozen=True)
class Phone:
    """A phone, in millimetres. See the honesty warning in the module docstring."""

    name: str
    length: float
    width: float
    thickness: float
    #: Radius of the body's rounded corners in plan.
    corner_radius: float

    #: How the camera is arranged on the back, which decides where the
    #: opening goes as well as how big it is:
    #:
    #: ``corner``
    #:     An island in one corner -- a square for the 13-16 Pro, a vertical
    #:     pill for the 15/16, a small diagonal pair before that. The opening
    #:     is measured in from the body's top and side edges.
    #: ``plateau``
    #:     The bar across the whole width of the back, introduced on the 17
    #:     Pro. It is *centred*, not cornered, and it reaches close enough to
    #:     both side edges that a case is left holding the top of its back
    #:     plate on a narrow strip. Placing one of these as a corner island
    #:     puts plastic over two of the three lenses.
    camera_style: str = "corner"
    #: Camera opening: size, corner radius, and (``corner`` style only) the
    #: gap from the body's top and side edges to the nearest edge of it.
    camera_w: float = 38.0
    camera_h: float = 38.0
    camera_r: float = 11.0
    camera_margin_top: float = 3.0
    camera_margin_side: float = 3.0

    #: USB-C / Lightning opening, centred on the bottom edge.
    port_w: float = 13.0
    port_h: float = 9.0

    #: Speaker and mic grille openings, as offsets from the bottom centre.
    speaker_offset: float = 18.0
    speaker_w: float = 16.0
    speaker_h: float = 4.0

    #: Side buttons, as (name, face, centre offset along the face, length).
    buttons: tuple[tuple[str, str, float, float], ...] = (
        ("power", "right", 6.0, 26.0),
        ("volume-up", "left", 22.0, 14.0),
        ("volume-down", "left", 5.0, 14.0),
        ("action", "left", 38.0, 9.0),
    )

    def cutouts(self, *, back_thickness: float, cavity_depth: float,
                clearance: float, buttons: bool = True) -> list[Cutout]:
        """The standard hole set for this phone, in case coordinates."""
        # Camera. A corner island is measured in from the top and from the
        # +x side of the body -- it lives on the phone's back and this frame
        # is a front view, so it is at +x. A plateau spans the width and is
        # centred, so only the top margin places it.
        if self.camera_style == "plateau":
            cx = 0.0
        else:
            cx = self.width / 2 - self.camera_margin_side - self.camera_w / 2
        cy = self.length / 2 - self.camera_margin_top - self.camera_h / 2
        out = [Cutout("camera", "back", cx, cy,
                      self.camera_w, self.camera_h, self.camera_r)]

        # Side holes are centred on the phone body, which starts one back
        # plate up from z=0. Leave the port open to the rim so a thick cable
        # end has somewhere to go.
        mid = back_thickness + cavity_depth / 2
        port_h = min(self.port_h, cavity_depth)
        out.append(Cutout("port", "bottom", 0.0, mid,
                          self.port_w, port_h, min(3.0, port_h / 2)))
        for sign in (-1, 1):
            out.append(Cutout(f"speaker{'+' if sign > 0 else '-'}", "bottom",
                              sign * self.speaker_offset, mid,
                              self.speaker_w, min(self.speaker_h, cavity_depth),
                              min(self.speaker_h, cavity_depth) / 2))
        if buttons:
            # Stadium shaped, not rectangular: the top of a side cutout is a
            # bridge across open air, and an arch halves how much of it is
            # flat. Also cut a little wider than the button itself, so a
            # thumb can reach in.
            for name, face, offset, length in self.buttons:
                h = min(cavity_depth - 0.6, 7.0)
                out.append(Cutout(name, face, offset, mid,
                                  length + 2 * clearance, h, h / 2))
        return out


@dataclass
class CaseSpec:
    """Every dimension of the case, in mm."""

    phone: Phone

    # --- fit -----------------------------------------------------------
    #: Gap between the phone and the inside of the case, all the way round.
    #: Under ~0.2 and it will not go on; over ~0.6 and it rattles.
    clearance: float = 0.35
    #: Side wall thickness.
    wall: float = 1.7
    #: Back plate thickness.
    back_thickness: float = 1.3
    #: How far the wall rises past the screen, to keep glass off a table.
    lip: float = 1.2
    #: How far the wall leans in over the screen at the very top.
    lip_inset: float = 0.9
    #: 45-degree break on the outer bottom edge. Prints clean and feels made.
    base_chamfer: float = 0.6

    # --- the print ------------------------------------------------------
    nozzle: float = 0.4
    line_width: float = 0.42
    layer_height: float = 0.2
    first_layer_height: float = 0.24
    #: Bottom layers printed as solid: this is the back plate's visible face.
    #: Only the first ``art_layers`` of them carry the artwork.
    art_layers: int = 2
    #: Perimeter loops around the edge of the back plate and around its holes.
    plate_perimeters: int = 3

    # --- holes ----------------------------------------------------------
    cutouts: list[Cutout] = field(default_factory=list)

    # --- section solver --------------------------------------------------
    #: Grid pitch of the distance field the perimeters are traced from (mm).
    #: 0.3 is invisible at a 0.42 line; raise it if you are in a hurry.
    section_res: float = 0.3

    def __post_init__(self) -> None:
        if not self.cutouts:
            self.cutouts = self.phone.cutouts(
                back_thickness=self.back_thickness,
                cavity_depth=self.cavity_depth,
                clearance=self.clearance)

    # -- derived ---------------------------------------------------------

    @property
    def cavity_depth(self) -> float:
        """Depth of the pocket the phone drops into."""
        return self.phone.thickness + self.clearance

    @property
    def inner_w(self) -> float:
        return self.phone.width + 2 * self.clearance

    @property
    def inner_l(self) -> float:
        return self.phone.length + 2 * self.clearance

    @property
    def inner_r(self) -> float:
        return self.phone.corner_radius + self.clearance

    @property
    def outer_w(self) -> float:
        return self.inner_w + 2 * self.wall

    @property
    def outer_l(self) -> float:
        return self.inner_l + 2 * self.wall

    @property
    def outer_r(self) -> float:
        return self.inner_r + self.wall

    @property
    def height(self) -> float:
        """Total printed height."""
        return self.back_thickness + self.cavity_depth + self.lip

    @property
    def wall_pairs(self) -> int:
        """Perimeter loops per side of the wall.

        The wall is traced out of a distance field, and a contour at a given
        depth comes back as *two* loops, one measured in from each face. So
        the count that matters is the count per side, and the wall always
        ends up with an even number of perimeters.
        """
        return max(1, int(round((self.wall / 2) / self.line_width)))

    @property
    def perimeters(self) -> int:
        """Perimeter loops across the whole side wall."""
        return 2 * self.wall_pairs

    @property
    def wall_line(self) -> float:
        """Extrusion width of a wall perimeter.

        Solved from the wall thickness rather than chosen, so the loops span
        the wall exactly however thick it is -- no void up the middle of the
        wall and no over-packed wall that bows outwards.
        """
        return (self.wall / 2) / self.wall_pairs


    @property
    def solid_layers(self) -> int:
        """Back plate layers, including the artwork layers."""
        usable = self.back_thickness - self.first_layer_height
        return max(1, 1 + int(round(usable / self.layer_height)))

    @property
    def lip_overhang_deg(self) -> float:
        """How far the lip leans in, from vertical. Over ~50 and it droops."""
        if self.lip <= 0 or self.lip_inset <= 0:
            return 0.0
        return math.degrees(math.atan(self.lip_inset / self.lip))

    def layer_zs(self) -> list[tuple[float, float]]:
        """``(z_top, layer_height)`` for every layer, bottom to top."""
        out = [(self.first_layer_height, self.first_layer_height)]
        z = self.first_layer_height
        while z < self.height - 1e-9:
            h = min(self.layer_height, self.height - z)
            if h < self.layer_height * 0.4:
                break  # a sliver of a top layer is worse than no top layer
            z += h
            out.append((z, h))
        return out

    def inner_inset_at(self, z: float) -> float:
        """How far the cavity wall leans in at height ``z``.

        Zero over the body of the case, ramping to ``lip_inset`` across the
        lip. Ramped rather than stepped because a step is a 90-degree
        overhang and a ramp is an overhang you can actually print.
        """
        top = self.height
        if self.lip <= 0 or z <= top - self.lip:
            return 0.0
        return self.lip_inset * (z - (top - self.lip)) / self.lip

    def outer_inset_at(self, z: float) -> float:
        """How far the outer surface is pulled in at height ``z``.

        Only the chamfer at the base, which slopes outward as it climbs and so
        needs no support.
        """
        if self.base_chamfer > 0 and z < self.base_chamfer:
            return self.base_chamfer - z
        return 0.0


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

@dataclass
class CaseReport:
    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_case(spec: CaseSpec, *, bed: tuple[float, float, float] | None = None,
               slots: int | None = None, used_slots: int = 1) -> CaseReport:
    """Everything that would make this case not worth printing.

    Split into problems (the generator refuses) and warnings (it prints and
    tells you). The line between them is whether the part comes off the bed
    useless or merely imperfect.
    """
    problems: list[str] = []
    warnings: list[str] = []
    lw = spec.line_width

    if spec.clearance < 0.15:
        problems.append(
            f"clearance {spec.clearance:.2f} mm is tighter than the process: "
            "the case will not go on. 0.3-0.4 is the usual landing spot")
    elif spec.clearance > 0.7:
        warnings.append(
            f"clearance {spec.clearance:.2f} mm will rattle; try 0.35")

    if spec.wall < 2 * lw - 1e-9:
        problems.append(
            f"wall {spec.wall:.2f} mm is under two {lw:.2f} mm lines, so it "
            "cannot be printed as perimeters at all")
    elif spec.wall < 1.2:
        warnings.append(
            f"wall {spec.wall:.2f} mm is thin; it will flex on and off the "
            "phone but it will also split at a corner eventually")

    if spec.back_thickness < 3 * spec.layer_height:
        problems.append(
            f"back plate {spec.back_thickness:.2f} mm is under three layers; "
            "the artwork will show the infill through it")
    if spec.art_layers > spec.solid_layers:
        problems.append(
            f"art_layers ({spec.art_layers}) exceeds the {spec.solid_layers} "
            "solid layers in the back plate")

    if spec.lip_overhang_deg > 50:
        problems.append(
            f"the lip leans in at {spec.lip_overhang_deg:.0f} degrees from "
            f"vertical ({spec.lip_inset:.2f} mm over {spec.lip:.2f} mm); "
            "raise --lip or lower --lip-inset")
    elif spec.lip_overhang_deg > 40:
        warnings.append(
            f"the lip leans in at {spec.lip_overhang_deg:.0f} degrees; "
            "it will print but the top edge will be rough")
    if spec.lip > 0 and spec.lip_inset <= 0:
        warnings.append("lip_inset is 0, so the lip does not hold the phone in")

    # Cutouts.
    half_w, half_l = spec.outer_w / 2, spec.outer_l / 2
    for c in spec.cutouts:
        if c.face == "back":
            # A back cutout that reaches the wall turns the case into two
            # halves joined by a strip. Measure the strip.
            left = half_w - (abs(c.u) + c.w / 2)
            below = half_l - (abs(c.v) + c.h / 2)
            if min(left, below) < 0:
                problems.append(
                    f"{c.name} cutout runs off the back of the case")
            elif min(left, below) < spec.wall + 2 * lw:
                warnings.append(
                    f"{c.name} cutout leaves only {min(left, below):.1f} mm "
                    "of back plate at the edge; it will be fragile there")
        else:
            span = spec.outer_w if c.face in ("top", "bottom") else spec.outer_l
            if abs(c.u) + c.w / 2 > span / 2:
                problems.append(f"{c.name} cutout runs off the {c.face} edge")
            if c.v + c.h / 2 > spec.height + 1e-6:
                warnings.append(
                    f"{c.name} cutout is open at the rim (it reaches "
                    f"{c.v + c.h / 2:.1f} mm of {spec.height:.1f} mm)")
            if c.v - c.h / 2 < spec.back_thickness - 0.3:
                warnings.append(
                    f"{c.name} cutout would cut into the back plate; it has "
                    "been stopped flat at the plate, which leaves a square "
                    "bottom corner rather than a rounded one")
            # The top of a side cutout bridges open air. A wall strip of
            # this width bridges further than a solid layer would, but not
            # indefinitely.
            if c.flat_top_span > 20.0:
                warnings.append(
                    f"{c.name} bridges {c.flat_top_span:.0f} mm unsupported "
                    "across its top; raise its corner radius or print slow")

    seen: dict[str, list[Cutout]] = {}
    for c in spec.cutouts:
        seen.setdefault(c.face, []).append(c)
    for face, group in seen.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if (abs(a.u - b.u) < (a.w + b.w) / 2
                        and abs(a.v - b.v) < (a.h + b.h) / 2):
                    warnings.append(
                        f"{a.name} and {b.name} overlap on the {face} face; "
                        "they will merge into one opening")

    if bed is not None:
        bx, by, bz = bed
        if spec.outer_w + 6 > bx or spec.outer_l + 6 > by:
            problems.append(
                f"case is {spec.outer_w:.0f} x {spec.outer_l:.0f} mm and does "
                f"not fit a {bx:.0f} x {by:.0f} mm bed")
        if spec.height > bz:
            problems.append(f"case is taller than the {bz:.0f} mm z limit")

    if slots is not None and used_slots > slots:
        problems.append(
            f"the artwork needs {used_slots} colours but the printer has "
            f"{slots} slots loaded")

    return CaseReport(not problems, problems, warnings)


# --------------------------------------------------------------------------
# the phones
# --------------------------------------------------------------------------

def _pro(name, length, width, thickness) -> Phone:
    """Three-camera square island, action button in place of the mute switch."""
    return Phone(name=name, length=length, width=width, thickness=thickness,
                 corner_radius=11.5,
                 camera_w=39.0, camera_h=39.0, camera_r=11.5,
                 camera_margin_top=3.0, camera_margin_side=3.0)


def _plateau(name, length, width, thickness, *, height=25.0,
             margin_side=2.0, margin_top=2.5) -> Phone:
    """The 17-generation bar: full width of the back rather than a corner.

    Sized from the body rather than given as a number, because what makes it
    a plateau is that it runs to both edges. What is left of the back plate
    beside it is ``margin_side`` plus the case wall, and above it
    ``margin_top`` plus the wall -- a few millimetres either way, which
    ``check_case`` measures and complains about if the fit makes it thinner.
    """
    return Phone(name=name, length=length, width=width, thickness=thickness,
                 corner_radius=12.0, camera_style="plateau",
                 camera_w=width - 2 * margin_side, camera_h=height,
                 camera_r=min(height / 2, 12.0),
                 camera_margin_top=margin_top, camera_margin_side=margin_side)


def _base(name, length, width, thickness, *, pill=True) -> Phone:
    """Two cameras: a vertical pill on the 15/16 generation, diagonal before."""
    if pill:
        cw, ch, cr = 27.0, 47.0, 13.5
    else:
        cw, ch, cr = 34.0, 34.0, 10.0
    return Phone(name=name, length=length, width=width, thickness=thickness,
                 corner_radius=11.0,
                 camera_w=cw, camera_h=ch, camera_r=cr,
                 camera_margin_top=3.0, camera_margin_side=3.0)


#: Body sizes are published specs. Camera and button figures are estimates --
#: see the module docstring, and print ``--test-fit`` before you trust them.
PHONES: dict[str, Phone] = {
    "iphone-13":         _base("iPhone 13", 146.7, 71.5, 7.65, pill=False),
    "iphone-13-pro":     _pro("iPhone 13 Pro", 146.7, 71.5, 7.65),
    "iphone-14":         _base("iPhone 14", 146.7, 71.5, 7.80, pill=False),
    "iphone-14-pro":     _pro("iPhone 14 Pro", 147.5, 71.5, 7.85),
    "iphone-14-pro-max": _pro("iPhone 14 Pro Max", 160.7, 77.6, 7.85),
    "iphone-15":         _base("iPhone 15", 147.6, 71.6, 7.80),
    "iphone-15-plus":    _base("iPhone 15 Plus", 160.9, 77.8, 7.80),
    "iphone-15-pro":     _pro("iPhone 15 Pro", 146.6, 70.6, 8.25),
    "iphone-15-pro-max": _pro("iPhone 15 Pro Max", 159.9, 76.7, 8.25),
    "iphone-16":         _base("iPhone 16", 147.6, 71.6, 7.80),
    "iphone-16-plus":    _base("iPhone 16 Plus", 160.9, 77.8, 7.80),
    "iphone-16-pro":     _pro("iPhone 16 Pro", 149.6, 71.5, 8.25),
    "iphone-16-pro-max": _pro("iPhone 16 Pro Max", 163.0, 77.6, 8.25),
    # The 17 Pro moved the cameras into a bar across the whole width of the
    # back. Sizes below are estimates like every other camera figure here,
    # but the *shape* is not a guess: a corner island on one of these covers
    # two of the three lenses.
    "iphone-17":         _base("iPhone 17", 149.6, 71.5, 7.95),
    "iphone-17-pro":     _plateau("iPhone 17 Pro", 150.0, 71.9, 8.75),
    "iphone-17-pro-max": _plateau("iPhone 17 Pro Max", 163.4, 78.0, 8.75),
    # One camera, and the thinnest body Apple has shipped, so the cavity is
    # shallow and the lip does more of the work of holding it in.
    "iphone-air":        _plateau("iPhone Air", 156.2, 74.6, 5.64,
                                  height=22.0),
    "iphone-se-3":       Phone("iPhone SE (3rd gen)", 138.4, 67.3, 7.3,
                               corner_radius=9.0,
                               camera_w=17.0, camera_h=17.0, camera_r=6.0,
                               camera_margin_top=6.0, camera_margin_side=6.0,
                               buttons=(("power", "right", 6.0, 20.0),
                                        ("volume-up", "left", 20.0, 12.0),
                                        ("volume-down", "left", 4.0, 12.0),
                                        ("mute", "left", 34.0, 8.0))),
}
