"""iPads, for the phone case generator.

An iPad case is the same part as a phone case -- a back plate, a wall, a lip
that leans in over the glass, holes where the hardware is -- only bigger, so
this file does not have its own generator. It is a table of iPads written in
src/phonecase/'s terms, and the page at /ipad is the phone case page talking
to /api/ipad instead of /api/case.

It lives out here rather than in src/phonecase/spec.py because that package
is vendored (see PROVENANCE in src/case_app.py): editing it here would be
overwritten by the next copy across.

Three things are different from a phone, and they are why ``Tablet`` exists:

* **Speakers at both ends.** Every current iPad plays stereo in landscape, so
  there are grilles on the top edge as well as the bottom. ``Phone`` only
  cuts the bottom.
* **Buttons on the top edge.** The top button is always there; on the
  cheaper iPad and the mini the volume buttons are too, which is what
  ``Phone.buttons`` with a ``"top"`` face says.
* **The Pencil.** Every iPad from the mini up charges or parks its Pencil on
  magnets in the right-hand edge, and a wall of plastic between the two is
  the difference between it charging and not. ``pencil`` cuts the wall down
  over that stretch, open to the rim, so the Pencil sits on the iPad itself.

THE SAME WARNING AS THE PHONES, LOUDER. The body sizes below are Apple's
published figures. Everything else -- corner radius, camera opening, where
the buttons and grilles are, how long the Pencil stretch is -- is an estimate
from product photos, and nothing here has been measured against a real iPad.
The corner radii in particular are guessed on the small side on purpose: a
case corner tighter than the iPad's leaves a gap you will never notice, and
one looser than it pushes on the corner and the iPad does not go in. Print
the test fit before you print the case.

The frame is the phone's: ``x`` across, ``y`` along, as you look at the
screen in portrait with the USB-C port at the bottom. The rear camera is
top-left seen from behind, which is top-right (+x, +y) in this frame.
"""
from __future__ import annotations

from dataclasses import dataclass

from phonecase.spec import Cutout, Phone


@dataclass(frozen=True)
class Tablet(Phone):
    """A ``Phone`` with speakers at both ends and a place for the Pencil."""

    #: Grilles on the top edge, as (centre offset along the edge, length).
    #: The bottom ones are ``speaker_offset`` / ``speaker_w`` as on a phone.
    top_speakers: tuple[tuple[float, float], ...] = ()

    #: The Pencil's magnets on the right edge, as (centre offset along the
    #: edge, length), or ``None`` for an iPad without them.
    pencil: tuple[float, float] | None = None

    def cutouts(self, *, back_thickness: float, cavity_depth: float,
                clearance: float, buttons: bool = True,
                pencil: bool = True) -> list[Cutout]:
        out = super().cutouts(back_thickness=back_thickness,
                              cavity_depth=cavity_depth,
                              clearance=clearance, buttons=buttons)
        mid = back_thickness + cavity_depth / 2
        h = min(self.speaker_h, cavity_depth)
        for i, (u, w) in enumerate(self.top_speakers):
            out.append(Cutout(f"speaker-top{i + 1}", "top", u, mid, w, h, h / 2))
        if pencil and self.pencil is not None:
            u, length = self.pencil
            # Open to the rim rather than a window in the wall: a window
            # this long is a bridge the whole length of a Pencil, and the
            # Pencil wants to sit against the glass edge anyway. The bottom
            # stops 1.5 mm above the back plate, so the case still has a
            # ledge along there holding the iPad in from behind.
            lo = back_thickness + 1.5
            hi = back_thickness + cavity_depth + 4.0   # past the lip
            out.append(Cutout("pencil", "right", u, (lo + hi) / 2,
                              length, hi - lo, 1.5))
        return out


def _ipad(name, length, width, thickness, *, radius, camera, lenses=1,
          volume_on_top, pencil=None, speaker_w=20.0) -> Tablet:
    """One iPad, with the layout the whole range shares worked out from its size.

    ``camera`` is ``(w, h, r, margin)``, the margin the same from the top and
    the side. Button offsets are measured in from the +x end of the top edge,
    which is where the top button is on every iPad without a home button.
    """
    cw, ch, cr, cm = camera
    half_w, half_l = width / 2, length / 2
    top_button = ("top", "top", half_w - 20.0, 22.0)
    if volume_on_top:
        # Volume up and down on the top edge beside the top button, so the
        # top grille is only at the far end, clear of them.
        btns = (top_button,
                ("volume-up", "top", half_w - 46.0, 14.0),
                ("volume-down", "top", half_w - 63.0, 14.0))
        tops = ((-(half_w - 22.0), speaker_w),)
    else:
        # Volume on the right edge, near the top; grilles at both corners of
        # the top edge, the +x one inboard of the top button.
        btns = (top_button,
                ("volume-up", "right", half_l - 30.0, 14.0),
                ("volume-down", "right", half_l - 47.0, 14.0))
        tops = ((-(half_w - 22.0), speaker_w), (half_w - 52.0, speaker_w))
    return Tablet(
        name=name, length=length, width=width, thickness=thickness,
        corner_radius=radius, lenses=lenses,
        camera_w=cw, camera_h=ch, camera_r=cr,
        camera_margin_top=cm, camera_margin_side=cm,
        port_w=14.0, port_h=8.0,
        speaker_offset=half_w - 22.0, speaker_w=speaker_w, speaker_h=3.5,
        buttons=btns, top_speakers=tops, pencil=pencil)


def _pencil(length):
    """The Pencil stretch: centred on the right edge, about half its length.

    Long enough for the magnets and some room to land the Pencil either side
    of them; short enough to stop clear of volume buttons on that edge.
    """
    return (0.0, min(150.0, round(length * 0.52)))


#: Body sizes are published specs. Everything else is an estimate -- see the
#: module docstring, and print the test fit first.
IPADS: dict[str, Tablet] = {
    # USB-C, a single camera, volume on the top edge like the mini. The
    # 10th and 11th generation share a body.
    "ipad-11th-gen":   _ipad("iPad (A16)", 248.6, 179.5, 7.0, radius=17.0,
                             camera=(14.0, 14.0, 7.0, 7.0),
                             volume_on_top=True),
    "ipad-10th-gen":   _ipad("iPad (10th gen)", 248.6, 179.5, 7.0,
                             radius=17.0, camera=(14.0, 14.0, 7.0, 7.0),
                             volume_on_top=True),
    "ipad-mini-7":     _ipad("iPad mini (A17 Pro)", 195.4, 134.8, 6.3,
                             radius=14.0, camera=(14.0, 14.0, 7.0, 6.5),
                             volume_on_top=True, pencil=_pencil(195.4)),
    "ipad-mini-6":     _ipad("iPad mini (6th gen)", 195.4, 134.8, 6.3,
                             radius=14.0, camera=(14.0, 14.0, 7.0, 6.5),
                             volume_on_top=True, pencil=_pencil(195.4)),
    "ipad-air-11-m3":  _ipad("iPad Air 11\" (M2/M3)", 247.6, 178.5, 6.1,
                             radius=17.0, camera=(14.0, 14.0, 7.0, 7.0),
                             volume_on_top=False, pencil=_pencil(247.6)),
    "ipad-air-13-m3":  _ipad("iPad Air 13\" (M2/M3)", 280.6, 214.9, 6.1,
                             radius=18.0, camera=(14.0, 14.0, 7.0, 7.0),
                             volume_on_top=False, pencil=_pencil(280.6),
                             speaker_w=22.0),
    # The wide camera, the LiDAR and the flash in one rounded square. Drawn
    # as two lenses; the opening is what matters.
    "ipad-pro-11-m4":  _ipad("iPad Pro 11\" (M4/M5)", 249.7, 177.5, 5.3,
                             radius=17.0, camera=(24.0, 24.0, 8.0, 6.5),
                             lenses=2, volume_on_top=False,
                             pencil=_pencil(249.7)),
    "ipad-pro-13-m4":  _ipad("iPad Pro 13\" (M4/M5)", 281.6, 215.5, 5.1,
                             radius=18.0, camera=(24.0, 24.0, 8.0, 6.5),
                             lenses=2, volume_on_top=False,
                             pencil=_pencil(281.6), speaker_w=22.0),
}

#: Fits for something that weighs as much as four phones and is dropped
#: flat. Thicker all round than the phone presets, and ``slim`` is the
#: thinnest the back plate goes: 1 mm of PLA across a 180 x 250 mm plate
#: flexes like a playing card.
CASES: dict[str, dict] = {
    "snug": dict(clearance=0.4, wall=2.0, back_thickness=1.6, lip=1.4,
                 lip_inset=1.0),
    # The one that fits an 11-inch case in a 256 mm Bambu bed with room to
    # spare in a slicer.
    "slim": dict(clearance=0.35, wall=1.6, back_thickness=1.3, lip=1.0,
                 lip_inset=0.8),
    "rugged": dict(clearance=0.45, wall=2.6, back_thickness=2.0, lip=2.2,
                   lip_inset=1.3),
    "test": dict(clearance=0.55, wall=1.8, back_thickness=1.4, lip=1.2,
                 lip_inset=0.8),
}
