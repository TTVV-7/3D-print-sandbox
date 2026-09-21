"""Render the case to a standalone SVG before committing filament to it.

Three panels, and the first one is the only reliable answer to "will the
artwork come out the right way round":

* **back** -- the actual first-layer toolpath, every run stroked in the
  colour of the slot it is assigned to, flipped back into the orientation
  you will hold the case in. Not a re-render of the source SVG: if the
  mirror is wrong, or a shape landed in the camera hole, this is where it
  shows.
* **plan** -- the same case from the same side, with the phone dashed inside
  it and the lenses drawn into the camera opening. The lenses are an
  illustration of what sits behind the hole rather than geometry, and they
  are there because a rounded rectangle with a rounded rectangle cut out of
  it is the same picture for every phone.
* **side** -- the bottom and left edges unrolled, which is the only view
  where the port and the buttons are the right shape.
"""

from __future__ import annotations

from .paint import PaintPlan
from .spec import CaseSpec
from .toolpath import CasePath


PAD = 12.0
INK = "#2c2c33"
MUTED = "#8a8a92"
FAINT = "#d8d8de"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _label(x, y, text, size=7.5, col=MUTED, weight=400, anchor="middle") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{col}" '
            f'font-weight="{weight}" text-anchor="{anchor}" '
            f'font-family="ui-monospace,SFMono-Regular,Menlo,monospace">'
            f'{_esc(text)}</text>')


def _rrect(cx, cy, w, h, r, **attrs) -> str:
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return (f'<rect x="{cx - w / 2:.2f}" y="{cy - h / 2:.2f}" width="{w:.2f}" '
            f'height="{h:.2f}" rx="{r:.2f}" {a}/>')


def _back(spec: CaseSpec, path: CasePath, plan: PaintPlan) -> str:
    """First-layer toolpath, mirrored into the orientation you hold.

    The back face carries its own size in millimetres, and the runs are in a
    group of their own, so a page showing this can work out how far a drag
    moved the artwork and slide it under the outline while it waits for the
    real answer.
    """
    parts = [_rrect(0, 0, spec.outer_w, spec.outer_l, spec.outer_r,
                    fill="#f1f1f4", stroke="none", id="backface",
                    data_mm_w=f"{spec.outer_w:.3f}",
                    data_mm_l=f"{spec.outer_l:.3f}")]
    by_slot: dict[int, list[str]] = {}
    for layer in path.layers[:max(1, spec.art_layers)]:
        for run in layer.runs:
            if run.kind in ("skirt", "brim") or len(run.pts) < 2:
                continue
            pts = run.pts + [run.pts[0]] if run.closed else run.pts
            # Printed face down: flip x to see it the way it comes out.
            d = "M" + "L".join(f"{-x:.2f} {-y:.2f}" for x, y in pts)
            by_slot.setdefault(run.slot, []).append(d)
    parts.append('<g id="art-runs">')
    for slot, ds in sorted(by_slot.items()):
        col = plan.palette.slots[slot].hex if slot < len(plan.palette) else "#888"
        parts.append(
            f'<path d="{"".join(ds)}" fill="none" stroke="{col}" '
            f'stroke-width="{spec.line_width:.2f}" stroke-linecap="round" '
            f'stroke-linejoin="round"/>')
    parts.append('</g>')
    for c in spec.cutouts:
        if c.face == "back":
            parts.append(_rrect(-c.u, -c.v, c.w, c.h, c.r, fill="#ffffff",
                                stroke=MUTED, stroke_width="0.4",
                                stroke_dasharray="1.6 1.2"))
    parts.append(_rrect(0, 0, spec.outer_w, spec.outer_l, spec.outer_r,
                        fill="none", stroke=INK, stroke_width="0.5"))
    return "\n".join(parts)


def _lens_layout(phone, cam) -> list[tuple[float, float, float, bool]]:
    """Where the lenses sit inside the opening, as ``(dx, dy, r, is_lens)``.

    Offsets are from the centre of the cutout, in case coordinates. This is
    an illustration of what is behind the hole, not geometry -- the hole is
    the cutout and nothing here changes it. It is in the preview because a
    picture of a rounded rectangle with a rounded rectangle cut out of it is
    the same picture for every phone, and which phone it is was the one
    thing you could not see.
    """
    w, h = cam.w, cam.h
    if phone.camera_style == "plateau":
        # The cluster sits at one end of the bar. That end is the phone's +x
        # in this frame, which is the side the lenses are on when you turn
        # the phone over.
        r = min(h, w) * 0.21
        cx = w / 2 - h * 0.52
        out = [(cx + r * 0.95, r * 0.62, r, True),
               (cx - r * 0.95, r * 0.62, r, True),
               (cx, -r * 1.05, r, True)][:phone.lenses]
        if phone.lenses == 1:
            out = [(cx, 0.0, min(h, w) * 0.27, True)]
        out.append((-w / 2 + h * 0.42, 0.0, h * 0.11, False))   # flash
        return out

    if phone.lenses >= 3:
        r = min(w, h) * 0.19
        return [(-r * 1.05, r * 1.05, r, True), (-r * 1.05, -r * 1.05, r, True),
                (r * 1.05, -r * 1.05, r, True),
                (r * 1.15, r * 1.25, r * 0.42, False)]          # flash
    if phone.lenses == 2 and h > w * 1.4:                        # vertical pill
        r = w * 0.32
        return [(0.0, r * 1.05, r, True), (0.0, -r * 1.05, r, True)]
    if phone.lenses == 2:                                        # diagonal pair
        r = min(w, h) * 0.23
        return [(-r * 0.9, r * 0.9, r, True), (r * 0.9, -r * 0.9, r, True)]
    return [(0.0, 0.0, min(w, h) * 0.32, True)]


def _plan(spec: CaseSpec) -> str:
    """The case seen from the back, so it matches the panel beside it."""
    parts = [
        _rrect(0, 0, spec.outer_w, spec.outer_l, spec.outer_r,
               fill="#fafafb", stroke=INK, stroke_width="0.5"),
        # The phone itself, so the fit is something you can see.
        _rrect(0, 0, spec.phone.width, spec.phone.length,
               spec.phone.corner_radius, fill="none", stroke=FAINT,
               stroke_width="0.4", stroke_dasharray="3 2"),
        _rrect(0, 0, spec.inner_w, spec.inner_l, spec.inner_r,
               fill="none", stroke=MUTED, stroke_width="0.4"),
        _rrect(0, 0, spec.inner_w - 2 * spec.lip_inset,
               spec.inner_l - 2 * spec.lip_inset,
               max(0.2, spec.inner_r - spec.lip_inset), fill="none",
               stroke=FAINT, stroke_width="0.4", stroke_dasharray="2 1.5"),
    ]
    for c in spec.cutouts:
        if c.face != "back":
            continue
        # Mirrored, like the panel beside it: both are the back of the case.
        parts.append(_rrect(-c.u, -c.v, c.w, c.h, c.r, fill="#ffffff",
                            stroke=INK, stroke_width="0.4"))
        if c.name == "camera":
            for dx, dy, r, is_lens in _lens_layout(spec.phone, c):
                parts.append(
                    f'<circle cx="{-(c.u + dx):.2f}" cy="{-(c.v + dy):.2f}" '
                    f'r="{r:.2f}" fill="{"#e6e6ea" if is_lens else "#f2f2f5"}" '
                    f'stroke="{MUTED}" stroke-width="0.3"/>')
                if is_lens:
                    parts.append(
                        f'<circle cx="{-(c.u + dx):.2f}" cy="{-(c.v + dy):.2f}" '
                        f'r="{r * 0.45:.2f}" fill="#c9c9d2"/>')
        else:
            parts.append(_label(-c.u, -c.v + 1.5, c.name, 3.0, MUTED))
    return "\n".join(parts)


#: The four walls, unrolled, and how wide each one is. All four, in an order
#: that pairs the two edges you hold: left and right first, then the ends.
#:
#: It used to be two of them -- bottom and left. Every cutout on the right
#: face was therefore absent from every panel of every preview, which is how
#: a power button sitting twenty millimetres from where the button actually
#: is went unnoticed through the whole of this generator's life, and how the
#: 16 and 17 generations went that whole time with no Camera Control opening
#: at all. A view that cannot show a mistake will not find one.
FACES = ("left", "right", "top", "bottom")


def _side(spec: CaseSpec) -> tuple[str, float]:
    """All four edges unrolled and stacked, with their cutouts.

    Returns the body and the vertical centre of what was drawn, so the caller
    can place it; it does not scale anything itself.
    """
    parts = []
    y = 0.0
    for face in FACES:
        span = spec.outer_w if face in ("top", "bottom") else spec.outer_l
        parts.append(
            f'<rect x="{-span / 2:.2f}" y="{y - spec.height:.2f}" '
            f'width="{span:.2f}" height="{spec.height:.2f}" fill="#fafafb" '
            f'stroke="{INK}" stroke-width="0.4"/>')
        parts.append(
            f'<line x1="{-span / 2:.2f}" y1="{y - spec.back_thickness:.2f}" '
            f'x2="{span / 2:.2f}" y2="{y - spec.back_thickness:.2f}" '
            f'stroke="{FAINT}" stroke-width="0.3"/>')
        for c in spec.cutouts:
            if c.face != face:
                continue
            lo = max(c.v - c.h / 2, spec.back_thickness)
            hi = c.v + c.h / 2
            parts.append(_rrect(c.u, y - (lo + hi) / 2, c.w, hi - lo,
                                min(c.r, (hi - lo) / 2), fill="#ffffff",
                                stroke=INK, stroke_width="0.35"))
            parts.append(_label(c.u, y - hi - 1.0, c.name, 2.6, MUTED))
        parts.append(_label(-span / 2, y + 3.2, face, 3.0, MUTED, anchor="start"))
        y += spec.height + 9.0
    # Content runs from -height (top of the first face) to the last label.
    return "\n".join(parts), (y - 9.0 + 3.2 - spec.height) / 2


def _side_height(spec: CaseSpec) -> float:
    """How tall the unrolled edges are, before scaling."""
    return len(FACES) * (spec.height + 9.0) - 9.0 + 3.2


def render(spec: CaseSpec, path: CasePath, plan: PaintPlan, *,
           stats: dict | None = None) -> str:
    """Build the full SVG document.

    All three panels are the case seen from the back, which is the side the
    artwork is on and the side you look at. Getting the plan mirrored the
    other way, as it was, put the camera on the left in one panel and the
    right in the one next to it.
    """
    w, l = spec.outer_w, spec.outer_l
    col_w = max(w + 2 * PAD, 168.0)
    # Four faces instead of two are twice as tall, so the scale comes from
    # the room there is rather than from a constant that used to fit.
    side_scale = min(2.2, (l + 2 * PAD) / max(1.0, _side_height(spec)))
    side_col = l * side_scale + 2 * PAD
    side_body, side_mid = _side(spec)
    total_h = l + 2 * PAD + 80
    total_w = col_w * 2 + side_col
    # One caption grid for all three panels, so the columns line up.
    r0, r1, r2, r3 = (total_h - 61, total_h - 47, total_h - 33, total_h - 14)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" '
        f'height="{total_h:.0f}" viewBox="0 0 {total_w:.1f} {total_h:.1f}">',
        f'<rect width="{total_w:.1f}" height="{total_h:.1f}" fill="#fbfbfc"/>',
    ]
    top = PAD + l / 2

    # 1. the artwork, as printed
    parts.append(f'<g transform="translate({col_w / 2:.1f},{top:.1f})">'
                 f'{_back(spec, path, plan)}</g>')
    parts.append(_label(col_w / 2, r0, spec.phone.name, 10, INK, 600))
    parts.append(_label(col_w / 2, r1, "back, as you will hold it"))
    used = sorted(plan.raster.used_slots())
    swatch_x = col_w / 2 - len(used) * 30 / 2
    for i, slot in enumerate(used):
        sl = plan.palette.slots[slot]
        x = swatch_x + i * 30
        parts.append(f'<rect x="{x:.1f}" y="{r2 - 7:.1f}" width="9" height="9" '
                     f'rx="1.5" fill="{sl.hex}" stroke="{FAINT}"/>')
        parts.append(_label(x + 11.5, r2, f"T{sl.index}", 7, MUTED,
                            anchor="start"))
    parts.append(_label(col_w / 2, r3,
                        f"{spec.art_layers} art layers of "
                        f"{spec.layer_height:.2f} mm"))

    # 2. the case and the phone in it
    lens = {1: "one lens", 2: "two lenses", 3: "three lenses"}.get(
        spec.phone.lenses, f"{spec.phone.lenses} lenses")
    parts.append(f'<g transform="translate({col_w * 1.5:.1f},{top:.1f})">'
                 f'{_plan(spec)}</g>')
    parts.append(_label(col_w * 1.5, r0, "plan, from the back", 10, INK, 600))
    parts.append(_label(col_w * 1.5, r1,
                        f"{w:.1f} x {l:.1f} x {spec.height:.1f} mm  "
                        f"wall {spec.wall:.2f}  gap {spec.clearance:.2f}"))
    parts.append(_label(col_w * 1.5, r2,
                        f"{spec.phone.camera_style} camera, {lens}"))
    # Only a whole-case build has these. The page's preview is two layers
    # deep by design, so it comes through the other way and says what the
    # dashes mean instead; a caller that has already built the toolpath (the
    # library's own report, or a batch run) passes them in.
    if stats:
        parts.append(_label(col_w * 1.5, r3,
                            f"{stats['grams']:.1f} g  {stats['layers']} layers  "
                            f"{stats['tool_changes']} tool changes"))
    else:
        parts.append(_label(col_w * 1.5, r3, "dashed: the phone, and the lip"))

    # 3. the edges
    sx = col_w * 2 + side_col / 2
    parts.append(f'<g transform="translate({sx:.1f},'
                 f'{top - side_mid * side_scale:.1f}) '
                 f'scale({side_scale:.3f})">{side_body}</g>')
    parts.append(_label(sx, r0, "edges, unrolled", 10, INK, 600))
    parts.append(_label(sx, r1,
                        f"lip {spec.lip:.1f} mm tall, {spec.lip_inset:.1f} mm in "
                        f"({spec.lip_overhang_deg:.0f} deg)"))
    parts.append(_label(sx, r2, f"{side_scale:.1f}x"))
    parts.append(_label(sx, r3, ", ".join(
        c.name for c in spec.cutouts if c.face != "back") or "no side cutouts"))
    parts.append('</svg>')
    return "\n".join(parts)
