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

The body dimensions are published spec-sheet figures. This file used to say
that the camera openings and the button positions were not published at all.
That was wrong, and it was the half worth being wrong about: Apple ship a
dimensioned drawing for every iPhone, and
:mod:`extract_iphone_dims <extract_iphone_dims>` reads it. What that buys, and
what it does not:

* **Body size and corner radius**: published, and the drawing agrees with the
  table below to the hundredth.
* **Camera Control's opening**: published and exact, including a thin-case
  keepout meant for precisely this. See the note above :data:`BUTTONS_PRO`.
* **Where each button sits along the edge**: on the one drawing sheet whose
  text Apple flattens to outlines before publishing. Still an estimate.
* **The camera opening**: never dimensioned as a case opening at all. Still an
  estimate, and the one most likely to be wrong for your phone.

So two of the four are settled and two are not. Every one of them is
overridable, and ``--test-fit`` exists so that finding out costs twenty
minutes instead of six hours. Print that first -- and if the phone is a
present and you cannot measure it, print that first twice.
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


# --------------------------------------------------------------------------
# what is down each side
# --------------------------------------------------------------------------
#
# WHERE THESE CAME FROM, which is a different answer than it was.
#
# Apple publish a dimensioned drawing for every iPhone, at
# developer.apple.com/download/files/accessories/dimensional-drawings/.
# `src/extract_iphone_dims.py` reads all twenty-seven of them. On four -- the
# 16, 16 Pro, 16 Pro Max and 17e -- the general-dimensions sheet is published
# as real text, and it labels the side features by name: ACTION BUTTON, (+)
# VOLUME BUTTON, (-) VOLUME BUTTON, SIDE BUTTON, CAMERA CONTROL. Each name
# sits at the end of a leader line whose other end touches the feature. So
# these are measured, to about a millimetre.
#
# TWO THINGS THE MEASUREMENTS SETTLED, both of which the old numbers had
# wrong in a way no amount of staring would have found:
#
# **Buttons are placed from the top of the body, not from its middle.** The
# side button came out at 48.74, 48.00 and 48.17 mm from the top on three
# phones 149.6, 163.0 and 146.7 mm long -- a spread of three quarters of a
# millimetre across fourteen millimetres of body length. Stored as an offset
# from the centre, as they were, that one button would have to be a different
# number on every model, and it was instead the same number on all of them.
#
# **Camera Control is placed from the bottom.** 43.10, 43.08 and 42.61 mm up
# from the bottom edge on the 16 Pro, 16 Pro Max and Air. Which makes sense
# once you see it: it is where an index finger lands holding the phone in
# landscape, and that is referenced to the end of the phone you hold.
#
# So a control is stored as the edge it is measured from and its distance
# from it, and `Phone.cutouts` turns that into this package's centre offset
# using the body length. Every one of the old offsets was a centre offset
# copied across seventeen phones of different lengths, which put the same
# button at a different place on each of them.
#
# WHAT MOVED, for a 149.6 mm body, against what this file used to say:
#
#     action         36.8 mm from the top -> 21.5   (15.3 mm up)
#     volume up      52.8                 -> 38.9   (13.9 mm up)
#     volume down    69.8                 -> 58.7   (11.1 mm up)
#     side button    47.8                 -> 48.4   (0.6 mm down)
#     camera control 97.8                 -> 106.6  (8.8 mm down)
#
# The side button had already been corrected, by reasoning about where a side
# button can possibly be, and the drawing put that correction within a
# millimetre. The three on the left had not been, and were all out by more
# than a centimetre.
#
# STILL ESTIMATED: how *long* each opening is. The drawings dimension the
# keepouts, not the buttons, and only for Camera Control. The lengths below
# are unchanged and unverified, which matters less than it sounds: an opening
# is cut a clearance oversize and stadium-shaped, and Camera Control's uses
# Apple's thin-case keepout, which is nearly twelve millimetres longer than
# the control it clears.

#: Which end of the body a control's distance is measured from.
TOP, BOTTOM = "top", "bottom"

#: ``(name, face, edge, distance from that edge, length)``, all in mm.
#: Measured on the iPhone 16 family; see the note above.
_POWER = ("power", "right", TOP, 48.4, 27.0)
_VOLUME = (("volume-up", "left", TOP, 38.9, 15.0),
           ("volume-down", "left", TOP, 58.7, 15.0))
_ACTION = ("action", "left", TOP, 21.5, 9.0)

#: The ring/silent switch, which every iPhone had until the 15 Pro. Shorter
#: than the Action button that replaced it, and it sits where that does.
_MUTE = ("mute", "left", TOP, 21.5, 8.0)

#: Camera Control, measured from the bottom edge. The opening is Apple's
#: thin-case keepout rather than the control: 29.70 mm long, against a
#: control nearer eighteen. That slack is deliberate -- it is what absorbs
#: the millimetre of uncertainty in the position.
_CAMERA_CONTROL = ("camera-control", "right", BOTTOM, 43.0, 29.7)

Control = tuple[str, str, str, float, float]

#: 12 through 15 non-Pro, and every Pro before the 15 Pro: a mute switch.
BUTTONS_MUTE: tuple[Control, ...] = (_POWER, *_VOLUME, _MUTE)

#: 15 Pro and 15 Pro Max, and the 16e and 17e: an Action button, no Camera
#: Control. The e models have the Action button and not the control.
BUTTONS_ACTION: tuple[Control, ...] = (_POWER, *_VOLUME, _ACTION)

#: The 16 and 17 generations proper, and the Air.
BUTTONS_CAMERA_CONTROL: tuple[Control, ...] = (
    _POWER, *_VOLUME, _ACTION, _CAMERA_CONTROL)

#: Camera Control is a touch surface, not a key. Apple's keepout is 6.32 mm
#: across at 0.4 mm out from the glass, and the case has to clear all of it
#: or the control is being pressed through plastic.
CAMERA_CONTROL_WIDTH: tuple[tuple[str, float], ...] = (("camera-control", 6.32),)

#: How far in from the edge the case may lean before it sits on the screen.
#: Apple print it on the drawings, in these words: "ALL AROUND EXTERIOR OF
#: HOUSING TO START OF FLAT AREA ON TOP SIDE OF PRODUCT". It came out at
#: 2.41 mm on both drawings that state it, so it is treated as general.
LIP_INSET_LIMIT = 2.41

#: "CASE THICKNESS ON BACKSIDE OF PRODUCT: 2.1 mm MAX TO ENSURE FULL
#: FUNCTIONALITY" -- which is MagSafe. A back plate thicker than this still
#: prints and still fits; the magnets just stop holding.
MAGSAFE_BACK_LIMIT = 2.1


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

    #: How many lenses sit behind that opening. Drawing only: the cutout is
    #: the opening, and this is what the preview puts inside it so that one
    #: phone's picture does not look like every other phone's.
    lenses: int = 2

    #: USB-C / Lightning opening, centred on the bottom edge.
    port_w: float = 13.0
    port_h: float = 9.0

    #: Speaker and mic grille openings, as offsets from the bottom centre.
    speaker_offset: float = 18.0
    speaker_w: float = 16.0
    speaker_h: float = 4.0

    #: Side buttons and touch controls, as
    #: ``(name, face, edge, distance from that edge, length)``, in mm.
    #:
    #: ``edge`` is :data:`TOP` or :data:`BOTTOM` -- which end of the body the
    #: distance is measured from, because that is how the hardware is laid
    #: out and it is not the same end for everything. Buttons are placed from
    #: the top; Camera Control from the bottom. :meth:`cutouts` turns that
    #: into this package's centre offset using the body length.
    #:
    #: These were centre offsets, copied unchanged across seventeen phones of
    #: different lengths, which is another way of saying they were in a
    #: different place on every one. See the note above :data:`BUTTONS_MUTE`.
    buttons: tuple[tuple[str, str, str, float, float], ...] = BUTTONS_MUTE

    #: How wide each named opening is across the face, when the default
    #: (``min(cavity_depth - 0.6, 7)``) is not enough. Camera Control is the
    #: only one so far: it is a touch surface rather than a key, and Apple
    #: publish a keepout for it that is wider than a button needs.
    button_widths: tuple[tuple[str, float], ...] = ()

    def cutouts(self, *, back_thickness: float, cavity_depth: float,
                clearance: float, buttons: bool = True) -> list[Cutout]:
        """The standard hole set for this phone, in case coordinates."""
        # Camera. A corner island is measured in from the top and from the
        # +x side of the body -- it lives on the phone's back and this frame
        # is a front view, so it is at +x.
        #
        # A plateau is centred, so the side margin cannot place it. It sizes
        # it instead: what makes a plateau a plateau is that it runs to both
        # edges, so the opening is the body less a margin at each side, and
        # the margin is the number you would actually reach for. It used to be
        # baked into ``camera_w`` when the phone was built, which left the
        # field on the form and the flag on the command line changing the
        # report and nothing else -- you could type any side margin you liked
        # and get a byte-identical case.
        cw = self.camera_w
        if self.camera_style == "plateau":
            cx = 0.0
            cw = max(4.0, self.width - 2 * self.camera_margin_side)
        else:
            cx = self.width / 2 - self.camera_margin_side - self.camera_w / 2
        cy = self.length / 2 - self.camera_margin_top - self.camera_h / 2
        out = [Cutout("camera", "back", cx, cy,
                      cw, self.camera_h, min(self.camera_r, cw / 2))]

        # Side holes are centred on the phone body, which starts one back
        # plate up from z=0, and are as tall as the cavity will allow. The
        # port is not open to the rim -- it stops under the lip, the same as
        # the buttons do -- so a cable with a moulded boot may foul the top
        # edge of the opening. Opening it to the rim would take the lip away
        # across the bottom of the case, which is worse.
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
            wide = dict(self.button_widths)
            for name, face, edge, away, length in self.buttons:
                # From the edge the hardware is referenced to, into this
                # package's offset from the body's centre.
                offset = (self.length / 2 - away if edge == TOP
                          else away - self.length / 2)
                h = min(cavity_depth - 0.6, 7.0)
                # A named width is a keepout that has to be cleared, so it
                # wins over the default -- but not over the cavity, which is
                # all the wall there is to cut through.
                if name in wide:
                    h = min(max(h, wide[name]), cavity_depth - 0.6)
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
        # A first layer thinner than the ones above it is the one combination
        # that does not work: it is the layer the whole case is standing on
        # and the layer the artwork is in. The API lets the layer height go to
        # 0.32 while this stayed pinned at 0.24, so ask for fine layers and
        # you got a first layer thinner than the rest of them. Keep it between
        # one layer and what the nozzle can put down in one pass.
        self.first_layer_height = min(
            max(self.first_layer_height, self.layer_height), self.nozzle * 0.75)
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
    if spec.lip_inset > LIP_INSET_LIMIT:
        warnings.append(
            f"the lip reaches {spec.lip_inset:.2f} mm in over the front, and "
            f"Apple's drawings put the flat area at {LIP_INSET_LIMIT:.2f} mm "
            "from the edge; past that the case is sitting on the screen")

    # Apple state this one in words on the drawing: "CASE THICKNESS ON
    # BACKSIDE OF PRODUCT: 2.1 mm MAX TO ENSURE FULL FUNCTIONALITY". The part
    # still prints and still fits -- the magnets just stop holding.
    if spec.back_thickness > MAGSAFE_BACK_LIMIT:
        warnings.append(
            f"the back plate is {spec.back_thickness:.2f} mm and MagSafe "
            f"wants {MAGSAFE_BACK_LIMIT:.1f} mm or less between the magnets "
            "and the phone; it will hold weakly or not at all")

    # A named keepout that the cavity is too shallow to cut. This is real on
    # the Air, which is thin enough that there is not 6.32 mm of wall there.
    for name, want in spec.phone.button_widths:
        got = next((c.h for c in spec.cutouts if c.name == name), None)
        if got is not None and got < want - 1e-6:
            warnings.append(
                f"{name} needs a {want:.2f} mm opening to clear Apple's "
                f"keepout and the cavity only allows {got:.2f} mm; it will be "
                "pressed through plastic at the edges")

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
            if c.name == "camera" and spec.phone.camera_style == "plateau":
                # A plateau opening runs nearly the full width of the back, so
                # what is left above it is a rib the length of the phone's
                # width, joined on at its two ends and nowhere else. The
                # general check above measures to the outer edge and so counts
                # the wall, which stands on end and is not what breaks -- the
                # flat plate beside and above the hole is. Measure that.
                flange = left - spec.wall
                rib = below - spec.wall
                if min(flange, rib) < 2 * lw:
                    problems.append(
                        f"the camera bar leaves {min(flange, rib):.1f} mm of "
                        f"back plate past the wall, under two {lw:.2f} mm "
                        "lines; there is nothing there to print. Raise the "
                        "camera side or top margin")
                elif min(flange, rib) < 4 * lw:
                    warnings.append(
                        f"the camera bar leaves a {min(flange, rib):.1f} mm "
                        "strip of back plate past the wall; it is the first "
                        "thing that will snap. Raise the camera margins, or "
                        "the wall, if you have the room")
                if rib > 0 and c.w / rib > 20:
                    warnings.append(
                        f"the strip above the camera bar is {c.w:.0f} mm long "
                        f"and {rib:.1f} mm deep, and is held at its two ends "
                        "only; expect it to flex when the case goes on")
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
#
# Every model is written out in full rather than leaning on a factory's
# defaults. The table used to be four numbers per phone -- name, length,
# width, thickness -- with everything else inherited, so three corner radii
# covered eighteen phones and one 39 x 39 camera island covered seven Pros
# from a 146.6 mm body to a 163.0 mm one. Splitting them out is what lets a
# wrong one be seen and fixed.
#
# Each entry says where its numbers come from:
#
#   spec   the published specification, and where a drawing prints its own
#          figure the two agree (16: 147.64 x 71.63 x 7.81 against a quoted
#          147.6 x 71.6 x 7.80)
#   drawn  measured off Apple's dimensional drawing
#   est    an estimate. Still an estimate when it is written per model: what
#          splitting it buys is that correcting one phone no longer silently
#          moves six others.
#
# Body sizes are `spec`. Button positions are `drawn` on the 16 family and
# carried across elsewhere. Camera openings are `est` everywhere -- the
# drawings dimension the lens keepouts, never the hole a case should cut.


def _phone(name, length, width, thickness, *, corner, camera, buttons,
           lenses=2, style="corner", port=(13.0, 9.0), speaker=(18.0, 16.0, 4.0),
           widths=()) -> Phone:
    """One phone. ``camera`` is ``(w, h, r, margin_top, margin_side)``."""
    cw, ch, cr, mt, ms = camera
    return Phone(name=name, length=length, width=width, thickness=thickness,
                 corner_radius=corner, camera_style=style, lenses=lenses,
                 camera_w=cw, camera_h=ch, camera_r=cr,
                 camera_margin_top=mt, camera_margin_side=ms,
                 port_w=port[0], port_h=port[1],
                 speaker_offset=speaker[0], speaker_w=speaker[1],
                 speaker_h=speaker[2],
                 buttons=buttons, button_widths=widths)


#: A Lightning port, which is a good deal smaller than USB-C. Every phone in
#: this table used to be cut the same 13 x 9 opening, including the four here
#: that have no USB-C port at all.
_LIGHTNING = (9.5, 6.5)
_USB_C = (13.0, 9.0)

#: The two-camera diagonal square, used from the 12 through the 15. The
#: vertical pill people think of as "the two-camera iPhone" only arrives with
#: the 16, for spatial video -- the 15 and 15 Plus were being cut a 27 x 47
#: slot for a camera that is a 34 x 34 square.
_DIAGONAL = (34.0, 34.0, 10.0, 3.0, 3.0)
_PILL = (27.0, 47.0, 13.5, 3.0, 3.0)
_ISLAND = (39.0, 39.0, 11.5, 3.0, 3.0)
_ISLAND_MAX = (41.5, 41.5, 12.0, 3.0, 3.0)
_ONE_LENS = (24.0, 24.0, 8.0, 3.0, 3.0)

PHONES: dict[str, Phone] = {
    # --- iPhone 12: flat sides, mute switch, Lightning --------------------
    "iphone-12": _phone(
        "iPhone 12", 146.7, 71.5, 7.40, corner=11.0, camera=_DIAGONAL,
        buttons=BUTTONS_MUTE, port=_LIGHTNING),
    "iphone-12-mini": _phone(
        "iPhone 12 mini", 131.5, 64.2, 7.40, corner=10.5, camera=_DIAGONAL,
        buttons=BUTTONS_MUTE, port=_LIGHTNING, speaker=(15.0, 13.0, 4.0)),
    "iphone-12-pro": _phone(
        "iPhone 12 Pro", 146.7, 71.5, 7.40, corner=11.0, camera=_ISLAND,
        lenses=3, buttons=BUTTONS_MUTE, port=_LIGHTNING),
    "iphone-12-pro-max": _phone(
        "iPhone 12 Pro Max", 160.8, 78.1, 7.40, corner=11.5,
        camera=_ISLAND_MAX, lenses=3, buttons=BUTTONS_MUTE, port=_LIGHTNING),

    # --- iPhone 13 --------------------------------------------------------
    "iphone-13": _phone(
        "iPhone 13", 146.7, 71.5, 7.65, corner=11.0, camera=_DIAGONAL,
        buttons=BUTTONS_MUTE, port=_LIGHTNING),
    "iphone-13-mini": _phone(
        "iPhone 13 mini", 131.5, 64.2, 7.65, corner=10.5, camera=_DIAGONAL,
        buttons=BUTTONS_MUTE, port=_LIGHTNING, speaker=(15.0, 13.0, 4.0)),
    "iphone-13-pro": _phone(
        "iPhone 13 Pro", 146.7, 71.5, 7.65, corner=11.0, camera=_ISLAND,
        lenses=3, buttons=BUTTONS_MUTE, port=_LIGHTNING),
    "iphone-13-pro-max": _phone(
        "iPhone 13 Pro Max", 160.8, 78.1, 7.65, corner=11.5,
        camera=_ISLAND_MAX, lenses=3, buttons=BUTTONS_MUTE, port=_LIGHTNING),

    # --- iPhone 14: still a mute switch, still Lightning -------------------
    "iphone-14": _phone(
        "iPhone 14", 146.7, 71.5, 7.80, corner=11.0, camera=_DIAGONAL,
        buttons=BUTTONS_MUTE, port=_LIGHTNING),
    "iphone-14-plus": _phone(
        "iPhone 14 Plus", 160.8, 78.1, 7.80, corner=11.5, camera=_DIAGONAL,
        buttons=BUTTONS_MUTE, port=_LIGHTNING),
    "iphone-14-pro": _phone(
        "iPhone 14 Pro", 147.5, 71.5, 7.85, corner=11.0, camera=_ISLAND,
        lenses=3, buttons=BUTTONS_MUTE, port=_LIGHTNING),
    "iphone-14-pro-max": _phone(
        "iPhone 14 Pro Max", 160.7, 77.6, 7.85, corner=11.5,
        camera=_ISLAND_MAX, lenses=3, buttons=BUTTONS_MUTE, port=_LIGHTNING),

    # --- iPhone 15: USB-C arrives; the Pros get the Action button ---------
    "iphone-15": _phone(
        "iPhone 15", 147.6, 71.6, 7.80, corner=11.0, camera=_DIAGONAL,
        buttons=BUTTONS_MUTE, port=_USB_C),
    "iphone-15-plus": _phone(
        "iPhone 15 Plus", 160.9, 77.8, 7.80, corner=11.5, camera=_DIAGONAL,
        buttons=BUTTONS_MUTE, port=_USB_C),
    "iphone-15-pro": _phone(
        "iPhone 15 Pro", 146.6, 70.6, 8.25, corner=11.0, camera=_ISLAND,
        lenses=3, buttons=BUTTONS_ACTION, port=_USB_C),
    "iphone-15-pro-max": _phone(
        "iPhone 15 Pro Max", 159.9, 76.7, 8.25, corner=11.5,
        camera=_ISLAND_MAX, lenses=3, buttons=BUTTONS_ACTION, port=_USB_C),

    # --- iPhone 16: the vertical pill, and Camera Control -----------------
    # Body figures here are the drawing's own: 147.64 x 71.63 x 7.81.
    "iphone-16": _phone(
        "iPhone 16", 147.6, 71.6, 7.80, corner=11.0, camera=_PILL,
        buttons=BUTTONS_CAMERA_CONTROL, widths=CAMERA_CONTROL_WIDTH),
    "iphone-16-plus": _phone(
        "iPhone 16 Plus", 160.9, 77.8, 7.80, corner=11.5, camera=_PILL,
        buttons=BUTTONS_CAMERA_CONTROL, widths=CAMERA_CONTROL_WIDTH),
    "iphone-16-pro": _phone(
        "iPhone 16 Pro", 149.6, 71.5, 8.25, corner=11.0, camera=_ISLAND,
        lenses=3, buttons=BUTTONS_CAMERA_CONTROL, widths=CAMERA_CONTROL_WIDTH),
    "iphone-16-pro-max": _phone(
        "iPhone 16 Pro Max", 163.0, 77.6, 8.25, corner=11.5,
        camera=_ISLAND_MAX, lenses=3, buttons=BUTTONS_CAMERA_CONTROL,
        widths=CAMERA_CONTROL_WIDTH),
    # One camera, an Action button, and no Camera Control.
    "iphone-16e": _phone(
        "iPhone 16e", 146.7, 71.5, 7.80, corner=11.0, camera=_ONE_LENS,
        lenses=1, buttons=BUTTONS_ACTION),

    # --- iPhone 17 --------------------------------------------------------
    "iphone-17": _phone(
        "iPhone 17", 149.6, 71.5, 7.95, corner=11.0, camera=_PILL,
        buttons=BUTTONS_CAMERA_CONTROL, widths=CAMERA_CONTROL_WIDTH),
    # 17e's own drawing prints 146.71 x 71.52 x 7.80.
    "iphone-17e": _phone(
        "iPhone 17e", 146.7, 71.5, 7.80, corner=11.0, camera=_ONE_LENS,
        lenses=1, buttons=BUTTONS_ACTION),
    # The bar across the back. Its width is set by the side margin, not by
    # camera_w -- see Phone.cutouts.
    "iphone-17-pro": _phone(
        "iPhone 17 Pro", 150.0, 71.9, 8.75, corner=12.0, style="plateau",
        camera=(67.9, 34.0, 12.0, 2.5, 2.0), lenses=3,
        buttons=BUTTONS_CAMERA_CONTROL, widths=CAMERA_CONTROL_WIDTH),
    "iphone-17-pro-max": _phone(
        "iPhone 17 Pro Max", 163.4, 78.0, 8.75, corner=12.0, style="plateau",
        camera=(74.0, 34.0, 12.0, 2.5, 2.0), lenses=3,
        buttons=BUTTONS_CAMERA_CONTROL, widths=CAMERA_CONTROL_WIDTH),
    # The thinnest body Apple has shipped, which is why its Camera Control
    # opening is the one that cannot reach Apple's keepout: there is not
    # 6.32 mm of wall to cut through. check_case says so.
    "iphone-air": _phone(
        "iPhone Air", 156.2, 74.6, 5.64, corner=12.0, style="plateau",
        camera=(70.6, 26.0, 12.0, 2.5, 2.0), lenses=1,
        buttons=BUTTONS_CAMERA_CONTROL, widths=CAMERA_CONTROL_WIDTH),

    # --- the odd one out --------------------------------------------------
    # A 2017 body: home button, small single camera, Lightning, mute switch,
    # and a side button that sits high because there is a home button below
    # the screen taking up the length.
    "iphone-se-3": _phone(
        "iPhone SE (3rd gen)", 138.4, 67.3, 7.30, corner=9.0,
        camera=(17.0, 17.0, 6.0, 6.0, 6.0), lenses=1,
        buttons=(("power", "right", TOP, 30.0, 20.0),
                 ("volume-up", "left", TOP, 36.0, 12.0),
                 ("volume-down", "left", TOP, 52.0, 12.0),
                 ("mute", "left", TOP, 22.0, 8.0)),
        port=_LIGHTNING, speaker=(15.0, 13.0, 4.0)),
}

