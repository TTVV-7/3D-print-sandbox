"""Engineering-drawing marks as 2D shapely geometry, for inlaying on a face.

Everything is drawn in "view" coordinates: x to the right and y up, as you
see the face when you look straight at it. That way text always reads the
right way round; the caller maps the view onto the face.

Line widths are set for printing, not for paper: a 0.4 mm nozzle needs about
0.7 mm to lay a line down cleanly as a colour change.
"""
import os, sys
import numpy as np
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import unary_union
from shapely import affinity

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from trace_text import trace  # noqa: E402

FONT = os.path.join(HERE, "..", "src", "fonts", "Poppins-Bold.ttf")
LW = 0.7                    # line width
ARROW_L, ARROW_W = 2.6, 1.6 # arrowhead length and width
TEXT_H = 3.6                # dimension text cap height


def _u(v):
    v = np.asarray(v, float); return v / np.linalg.norm(v)


def line(p, q, w=LW):
    return LineString([p, q]).buffer(w/2, cap_style="flat")


def polyline(pts, w=LW):
    return LineString(pts).buffer(w/2, cap_style="flat", join_style="round")


def arrow(tip, direction, length=ARROW_L, width=ARROW_W):
    """Filled arrowhead with its point at `tip`, pointing along `direction`."""
    d = _u(direction); n = np.array([-d[1], d[0]])
    tip = np.asarray(tip, float); base = tip - d*length
    return Polygon([tip, base + n*width/2, base - n*width/2])


def text(s, h=TEXT_H, center=(0, 0), angle=0.0, max_w=None, tracking=0.03):
    """`s` set in Poppins Bold, capitals `h` tall, centred on `center`."""
    g = unary_union(trace(s, FONT, tracking))
    ref = unary_union(trace("H", FONT)).bounds            # scale by a capital, so Ø or ° don't shrink it
    k = h / (ref[3] - ref[1])
    g = affinity.scale(g, k, k, origin=(0, 0))
    x0, y0, x1, y1 = g.bounds
    if max_w and x1 - x0 > max_w:
        g = affinity.scale(g, max_w/(x1 - x0), max_w/(x1 - x0), origin=(0, 0))
        x0, y0, x1, y1 = g.bounds
    g = affinity.translate(g, -(x0 + x1)/2, -h/2)          # baseline at -h/2, so the capitals centre on 0
    g = affinity.rotate(g, angle, origin=(0, 0))
    return affinity.translate(g, *center)


def text_width(s, h=TEXT_H):
    b = text(s, h).bounds
    return b[2] - b[0]


def readable(deg):
    """An angle for text along a line, turned so it never reads upside down."""
    deg = (deg + 180) % 360 - 180
    if deg > 90.01: deg -= 180
    if deg <= -90: deg += 180
    return deg


def dim(p1, p2, off, label, h=TEXT_H, ext=True, inside=True, text_off=0.0):
    """A linear dimension between feature points p1 and p2.

    The dimension line runs parallel to p1-p2, `off` to its left (negative for
    the right), with extension lines back to the features, arrowheads at both
    ends and the label set in a break in the middle of the line. inside=False
    puts the arrows outside, pointing in, for a span too short for them.
    """
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    d = _u(p2 - p1); n = np.array([-d[1], d[0]])
    a, b = p1 + n*off, p2 + n*off
    out = []
    if ext:
        s = np.sign(off) or 1
        for p, q in ((p1, a), (p2, b)):
            out.append(line(p + n*s*0.8, q + n*s*1.6))
    L = np.linalg.norm(b - a); mid = (a + b)/2
    ang = np.degrees(np.arctan2(d[1], d[0]))
    t = text(label, h, (0, 0), readable(ang))
    tw = text_width(label, h)
    if inside:
        out += [arrow(a, -d), arrow(b, d)]
        gap = tw/2 + 1.2
        if L/2 - gap > ARROW_L + 0.3:
            out += [line(a, mid - d*gap), line(mid + d*gap, b)]
            out.append(affinity.translate(t, *(mid + n*text_off)))
        else:                                               # no room: one line, text beside it
            out.append(line(a, b))
            out.append(affinity.translate(t, *(mid + n*(h/2 + 1.4)*(1 if off >= 0 else -1))))
    else:
        out += [arrow(a, d), arrow(b, -d), line(a - d*(ARROW_L + 3), a), line(b, b + d*(ARROW_L + 3)), line(a, b)]
        out.append(affinity.translate(t, *(mid + n*(h/2 + 1.4)*(1 if off >= 0 else -1))))
    return unary_union(out)


def center_mark(c, r_clear, arm=2.8):
    """The cross of short dashes round a hole's centre, kept clear of radius r_clear."""
    c = np.asarray(c, float); out = []
    for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        d = np.array(d, float)
        out.append(line(c + d*(r_clear + 1.0), c + d*(r_clear + 1.0 + arm)))
    return unary_union(out)


def cross(c, size=3.0):
    c = np.asarray(c, float)
    return unary_union([line(c - (size, 0), c + (size, 0)), line(c - (0, size), c + (0, size))])


def chain(p, q, dash=6.0, gap=1.4, dot=1.0, w=LW*0.85):
    """A centre line: long dash, gap, dot, gap."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    d = _u(q - p); L = np.linalg.norm(q - p); s = 0.0; out = []
    while s < L:
        e = min(s + dash, L); out.append(line(p + d*s, p + d*e, w)); s = e + gap
        if s < L:
            e = min(s + dot, L); out.append(line(p + d*s, p + d*e, w)); s = e + gap
    return unary_union(out)


def radius(center, r, deg, label, h=TEXT_H, inset=1.4):
    """Radius dimension: a line from the centre to the arc, arrow on the arc."""
    c = np.asarray(center, float); d = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    tip = c + d*(r - inset)
    out = [line(c + d*1.5, tip - d*0.5), arrow(tip, d), cross(c, 2.2)]
    n = np.array([-d[1], d[0]])
    a = readable(deg)
    pos = c + d*(r*0.48) + n*(h/2 + 1.2)*(1 if np.cos(np.radians(deg)) >= 0 else -1)
    out.append(text(label, h, pos, a))
    return unary_union(out)


def angle(vertex, r, a0, a1, label, h=TEXT_H):
    """Angle dimension: an arc of radius r about `vertex` from a0 to a1 degrees."""
    v = np.asarray(vertex, float)
    ts = np.radians(np.linspace(a0, a1, 40))
    pts = v + r*np.c_[np.cos(ts), np.sin(ts)]
    out = [polyline(pts[2:-2])]
    for t, s in ((ts[0], -1), (ts[-1], 1)):
        tip = v + r*np.array([np.cos(t), np.sin(t)])
        out.append(arrow(tip, s*np.array([-np.sin(t), np.cos(t)])))
    tm = np.radians((a0 + a1)/2)
    pos = v + (r + h*0.9 + 1.0)*np.array([np.cos(tm), np.sin(tm)])
    out.append(text(label, h, pos, readable(np.degrees(tm) - 90)))
    return unary_union(out)


def leader(tip, elbow, label, h=TEXT_H, right=True):
    """A note with a leader: arrow at `tip`, a kink at `elbow`, then the text."""
    tip, elbow = np.asarray(tip, float), np.asarray(elbow, float)
    s = 1 if right else -1
    shelf = elbow + (s*2.5, 0)
    tw = text_width(label, h)
    out = [arrow(tip, tip - elbow), line(tip + _u(elbow - tip)*1.5, elbow), line(elbow, shelf),
           text(label, h, shelf + (s*(tw/2 + 1.0), 0))]
    return unary_union(out)


def frame(x0, y0, x1, y1, w=LW):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]).exterior.buffer(w/2, join_style="mitre")
