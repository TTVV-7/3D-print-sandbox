"""Render the case to a standalone SVG before committing filament to it.

Three panels, and the first one is the only reliable answer to "will the
artwork come out the right way round":

* **back** -- the actual first-layer toolpath, every run stroked in the
  colour of the slot it is assigned to, flipped back into the orientation
  you will hold the case in. Not a re-render of the source SVG: if the
  mirror is wrong, or a shape landed in the camera hole, this is where it
  shows.
* **plan** -- the outline and every cutout, labelled and dimensioned.
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
    """First-layer toolpath, mirrored into the orientation you hold."""
    parts = [_rrect(0, 0, spec.outer_w, spec.outer_l, spec.outer_r,
                    fill="#f1f1f4", stroke="none")]
    by_slot: dict[int, list[str]] = {}
    for layer in path.layers[:max(1, spec.art_layers)]:
        for run in layer.runs:
            if run.kind in ("skirt", "brim") or len(run.pts) < 2:
                continue
            pts = run.pts + [run.pts[0]] if run.closed else run.pts
            # Printed face down: flip x to see it the way it comes out.
            d = "M" + "L".join(f"{-x:.2f} {-y:.2f}" for x, y in pts)
            by_slot.setdefault(run.slot, []).append(d)
    for slot, ds in sorted(by_slot.items()):
        col = plan.palette.slots[slot].hex if slot < len(plan.palette) else "#888"
        parts.append(
            f'<path d="{"".join(ds)}" fill="none" stroke="{col}" '
            f'stroke-width="{spec.line_width:.2f}" stroke-linecap="round" '
            f'stroke-linejoin="round"/>')
    for c in spec.cutouts:
        if c.face == "back":
            parts.append(_rrect(-c.u, -c.v, c.w, c.h, c.r, fill="#ffffff",
                                stroke=MUTED, stroke_width="0.4",
                                stroke_dasharray="1.6 1.2"))
    parts.append(_rrect(0, 0, spec.outer_w, spec.outer_l, spec.outer_r,
                        fill="none", stroke=INK, stroke_width="0.5"))
    return "\n".join(parts)


def _plan(spec: CaseSpec) -> str:
    parts = [
        _rrect(0, 0, spec.outer_w, spec.outer_l, spec.outer_r,
               fill="#fafafb", stroke=INK, stroke_width="0.5"),
        _rrect(0, 0, spec.inner_w, spec.inner_l, spec.inner_r,
               fill="none", stroke=MUTED, stroke_width="0.4"),
        _rrect(0, 0, spec.inner_w - 2 * spec.lip_inset,
               spec.inner_l - 2 * spec.lip_inset,
               max(0.2, spec.inner_r - spec.lip_inset), fill="none",
               stroke=FAINT, stroke_width="0.4", stroke_dasharray="2 1.5"),
    ]
    for c in spec.cutouts:
        if c.face == "back":
            parts.append(_rrect(c.u, -c.v, c.w, c.h, c.r, fill="#ffffff",
                                stroke=INK, stroke_width="0.4"))
            parts.append(_label(c.u, -c.v + 1.5, c.name, 3.0, MUTED))
    return "\n".join(parts)


def _side(spec: CaseSpec, scale: float) -> str:
    """Bottom and left edges unrolled, stacked, with their cutouts."""
    parts = []
    y = 0.0
    for face, span in (("bottom", spec.outer_w), ("left", spec.outer_l)):
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


def render(spec: CaseSpec, path: CasePath, plan: PaintPlan, *,
           stats: dict | None = None) -> str:
    """Build the full SVG document."""
    w, l = spec.outer_w, spec.outer_l
    # Wide enough for the captions, not just the drawing.
    col_w = max(w + 2 * PAD, 168.0)
    # The edge views are the small dimension of the case seen edge on, so
    # they are drawn several times up; everything else is 1:1.
    side_scale = 2.2
    side_col = l * side_scale + 2 * PAD
    side_body, side_mid = _side(spec, side_scale)
    total_h = l + 2 * PAD + 66
    total_w = col_w * 2 + side_col

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" '
        f'height="{total_h:.0f}" viewBox="0 0 {total_w:.1f} {total_h:.1f}">',
        f'<rect width="{total_w:.1f}" height="{total_h:.1f}" fill="#fbfbfc"/>',
    ]
    top = PAD + l / 2

    parts.append(f'<g transform="translate({col_w / 2:.1f},{top:.1f})">'
                 f'{_back(spec, path, plan)}</g>')
    parts.append(_label(col_w / 2, total_h - 46,
                        "back, as you will hold it", 9, INK, 600))
    used = sorted(plan.raster.used_slots())
    swatch_x = col_w / 2 - len(used) * 30 / 2
    for i, slot in enumerate(used):
        s = plan.palette.slots[slot]
        x = swatch_x + i * 30
        parts.append(f'<rect x="{x:.1f}" y="{total_h - 40:.1f}" width="9" '
                     f'height="9" rx="1.5" fill="{s.hex}" stroke="{FAINT}"/>')
        parts.append(_label(x + 11.5, total_h - 32.5, f"T{s.index}", 7, MUTED,
                            anchor="start"))
    parts.append(_label(col_w / 2, total_h - 19,
                        f"{spec.art_layers} art layers of "
                        f"{spec.layer_height:.2f} mm"))

    parts.append(f'<g transform="translate({col_w * 1.5:.1f},{top:.1f})">'
                 f'{_plan(spec)}</g>')
    parts.append(_label(col_w * 1.5, total_h - 46, spec.phone.name, 9, INK, 600))
    parts.append(_label(col_w * 1.5, total_h - 33,
                        f"{w:.1f} x {l:.1f} x {spec.height:.1f} mm  "
                        f"wall {spec.wall:.2f}  gap {spec.clearance:.2f}"))
    if stats:
        parts.append(_label(col_w * 1.5, total_h - 19,
                            f"{stats['grams']:.1f} g  {stats['layers']} layers  "
                            f"{stats['tool_changes']} tool changes"))

    sx = col_w * 2 + side_col / 2
    parts.append(f'<g transform="translate({sx:.1f},'
                 f'{top - side_mid * side_scale:.1f}) '
                 f'scale({side_scale:.3f})">{side_body}</g>')
    parts.append(_label(sx, total_h - 46, "edges, unrolled", 9, INK, 600))
    parts.append(_label(sx, total_h - 33,
                        f"lip {spec.lip:.1f} mm tall, {spec.lip_inset:.1f} mm in "
                        f"({spec.lip_overhang_deg:.0f} deg)"))
    parts.append(_label(sx, total_h - 19,
                        f"{side_scale:.1f}x -- the dashed line on the plan is "
                        "the lip"))
    parts.append('</svg>')
    return "\n".join(parts)
