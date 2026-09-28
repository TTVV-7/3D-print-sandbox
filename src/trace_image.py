"""Trace a raster logo -- a PNG, a JPEG, a WebP -- into flat colour regions.

    regions = trace_image.painted(open("logo.png", "rb").read())

The same answer trace_svg.painted() gives for an SVG: [(fill, geometry)], y
up, each colour's region clear of the others.  So a logo that only exists as
the picture on a website still becomes a part, in its own colours.

Four steps, all plain numpy and Pillow:

  1. **Size.**  Scaled so the longer side is MAX_PX.  On a 60 mm card that is
     about a tenth of a millimetre a pixel -- a quarter of a nozzle -- and it
     keeps the tracing to a fraction of a second.
  2. **Background.**  Transparent pixels are background.  An opaque image --
     a JPEG, a logo on a white square -- has the colour round its border taken
     as background instead, but only where it *connects to* the border: the
     white inside a red disc is part of the logo, and stays.
  3. **Colours.**  The logo's pixels are clustered (k-means, seeded the same
     way every time) into at most `colours` flat colours.  The in-between
     shades anti-aliasing leaves on every edge go to whichever side they are
     nearest, and a cluster holding next to nothing is folded into its
     neighbour, so a halo never becomes a colour of its own.
  4. **Tracing.**  Each colour's pixels become polygons -- row runs merged in
     2-D -- smoothed with a simplify that turns the pixel staircase into the
     straight or curved edge it was drawn as, and then grown a hair and
     clipped against each other so neighbouring colours meet without a seam.
"""
import base64
import io

import numpy as np
from PIL import Image, ImageOps
from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

MAX_PX = 480            # the longer side, in pixels, after scaling
ALPHA = 128             # at or under this alpha is background
BG_DIST = 42.0          # RGB distance under which a pixel matches the border colour
SPECK = 0.012           # a cluster under this share of the logo is folded away
SAME = 34.0             # clusters closer than this in RGB are one colour
FRINGE = 0.3           # a cluster with less core than this is an edge halo
SMOOTH = 0.2            # simplify tolerance after smoothing, in pixels


def decode(data):
    """Bytes, or a data: URL as a browser's FileReader writes it, as an RGBA
    image the right way up."""
    if isinstance(data, str):
        if data.startswith("data:"):
            data = data.split(",", 1)[1]
        data = base64.b64decode(data)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise ValueError("that image could not be read -- a PNG, JPEG or WebP "
                         "works, or an SVG") from exc
    img = ImageOps.exif_transpose(img).convert("RGBA")
    img.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
    return img


def runs(mask):
    """A boolean mask as polygons, y up, one unit a pixel: every horizontal
    run of set pixels is a box, runs repeated on the next row are stretched
    rather than duplicated, and the lot is merged."""
    h, w = mask.shape
    boxes, open_ = [], {}
    for y in range(h):
        row = np.concatenate([[False], mask[y], [False]])
        d = np.flatnonzero(np.diff(row.astype(np.int8)))
        now = {}
        for x0, x1 in zip(d[::2], d[1::2]):
            key = (int(x0), int(x1))
            now[key] = open_.pop(key, y)
        for (x0, x1), y0 in open_.items():
            boxes.append(box(x0, -y, x1, -y0))
        open_ = now
    for (x0, x1), y0 in open_.items():
        boxes.append(box(x0, -h, x1, -y0))
    return unary_union(boxes) if boxes else None


def smooth(shape):
    """Traced pixels as the smooth outline they were drawn as: every ring
    corner-cut, then simplified to drop the points that no longer earn their
    place."""
    out = []
    for poly in getattr(shape, "geoms", [shape]):
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        shell = Polygon(cut(poly.exterior))
        holes = [Polygon(cut(r)) for r in poly.interiors]
        g = shell.buffer(0)
        for h in holes:
            g = g.difference(h.buffer(0))
        out.append(g)
    return unary_union(out).simplify(SMOOTH, preserve_topology=True).buffer(0)


def cut(ring, passes=3):
    """Chaikin corner cutting on a closed ring: each pass replaces every edge
    with the points a quarter and three quarters along it.  On a pixel
    staircase that leaves the smooth edge the steps were sampling, and moves
    nothing by more than half a pixel -- so a real corner stays a corner,
    just not a razor's."""
    pts = np.asarray(ring.coords)[:-1]
    for _ in range(passes):
        nxt = np.roll(pts, -1, axis=0)
        new = np.empty((len(pts) * 2, 2))
        new[0::2] = 0.75 * pts + 0.25 * nxt
        new[1::2] = 0.25 * pts + 0.75 * nxt
        pts = new
    return pts


def border_colour(rgb):
    """The colour of the image's edge, if it has one: the median of the
    border pixels, provided most of them are close to it."""
    edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(float)
    med = np.median(edge, axis=0)
    close = np.linalg.norm(edge - med, axis=1) < BG_DIST
    return med if close.mean() > 0.6 else None


def background(img, keep_background):
    """(boolean mask of the background pixels, its colour as '#rrggbb' when
    it was an opaque colour rather than transparency)."""
    a = np.asarray(img)
    rgb, alpha = a[..., :3], a[..., 3]
    clear = alpha <= ALPHA
    if clear.mean() > 0.02 or keep_background:
        return clear, None
    colour = border_colour(rgb)
    if colour is None:
        return clear, None
    near = np.linalg.norm(rgb.astype(float) - colour, axis=2) < BG_DIST
    # Only the part of it that reaches the edge: trace the near-colour pixels
    # and keep the pieces that touch the frame.
    h, w = near.shape
    shape = runs(near)
    if shape is None:
        return clear, None
    frame = box(0, -h, w, 0).exterior.buffer(0.5)
    pieces = [p for p in getattr(shape, "geoms", [shape]) if p.intersects(frame)]
    if not pieces:
        return clear, None
    reach = unary_union(pieces)
    # Back to pixels: rasterise by row, sampling the centre of each pixel.
    from shapely import contains_xy
    ys, xs = np.mgrid[0:h, 0:w]
    inside = contains_xy(reach, xs.ravel() + 0.5, -(ys.ravel() + 0.5)).reshape(h, w)
    return clear | (inside & near), "#%02x%02x%02x" % tuple(int(round(v)) for v in colour)


def core(mask):
    """The share of a mask's pixels whose four neighbours are all in it too.
    A real colour is mostly core; the ring of in-between shades round an
    anti-aliased edge is all edge, and comes out near zero."""
    if not mask.any():
        return 0.0
    inner = mask[1:-1, 1:-1] & mask[:-2, 1:-1] & mask[2:, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:]
    return inner.sum() / mask.sum()


def kmeans(pixels, k, iters=12, seed=7):
    """Cluster centres for `pixels` (n x 3 floats): k-means++ seeding from a
    fixed seed, so the same logo always gives the same colours."""
    rng = np.random.default_rng(seed)
    if len(pixels) > 20000:
        pixels = pixels[rng.choice(len(pixels), 20000, replace=False)]
    centres = [pixels[rng.integers(len(pixels))]]
    for _ in range(1, k):
        d = np.min([np.sum((pixels - c) ** 2, axis=1) for c in centres], axis=0)
        if d.sum() == 0:
            break
        centres.append(pixels[rng.choice(len(pixels), p=d / d.sum())])
    centres = np.array(centres)
    for _ in range(iters):
        label = np.argmin(((pixels[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
        for i in range(len(centres)):
            if np.any(label == i):
                centres[i] = pixels[label == i].mean(axis=0)
    return centres


def painted(data, colours=4, keep_background=False, report=None):
    """[(fill, geometry)] for a raster logo, y up, one unit a pixel of the
    scaled image -- the caller scales it to millimetres.  `colours` is the
    most it will come out in.  An opaque background's colour goes in
    report["background"], if a `report` dict is handed in."""
    img = decode(data)
    bg, bg_colour = background(img, keep_background)
    if report is not None and bg_colour:
        report["background"] = bg_colour
    rgb = np.asarray(img)[..., :3].astype(float)
    fg = ~bg
    if fg.sum() < 16:
        raise ValueError("the image looks empty once its background is taken away")
    pixels = rgb[fg]
    centres = kmeans(pixels, max(1, int(colours)) + 2)

    def assign(px, cs):
        return np.argmin(((px[:, None, :] - cs[None]) ** 2).sum(-1), axis=1)

    # Fold away specks and near-twins, smallest first, until what is left is
    # distinct, substantial and no more than asked for.
    while len(centres) > 1:
        label = assign(pixels, centres)
        share = np.bincount(label, minlength=len(centres)) / len(pixels)
        dist = np.linalg.norm(centres[:, None] - centres[None], axis=2)
        np.fill_diagonal(dist, np.inf)
        full = np.full(fg.shape, -1)
        full[fg] = label
        solid = np.array([core(full == i) for i in range(len(centres))])
        if share.min() < SPECK:
            drop = int(np.argmin(share))
        elif solid.min() < FRINGE:
            drop = int(np.argmin(solid))
        elif len(centres) > colours or dist.min() < SAME:
            i, j = np.unravel_index(np.argmin(dist), dist.shape)
            drop = i if share[i] < share[j] else j
        else:
            break
        centres = np.delete(centres, drop, axis=0)

    label = np.full(bg.shape, -1)
    label[fg] = assign(pixels, centres)
    h, w = bg.shape
    regions = []
    for i, c in enumerate(centres):
        shape = runs(label == i)
        if shape is None:
            continue
        shape = smooth(shape)
        parts = [p for p in getattr(shape, "geoms", [shape]) if p.area > 6.0]
        if parts:
            hexc = "#%02x%02x%02x" % tuple(int(round(v)) for v in c)
            regions.append((hexc, unary_union(parts)))

    # Grow each colour by a fraction of a pixel and clip the others by it,
    # smallest region last so fine detail sits on top: neighbours then meet
    # along one edge rather than leaving a hairline of body between them.
    regions.sort(key=lambda r: -r[1].area)
    out = []
    for hexc, g in regions:
        g = g.buffer(0.45, join_style=2)
        out = [(k, o.difference(g)) for k, o in out]
        out.append((hexc, g))
    out = [(k, g) for k, g in out if not g.is_empty and g.area > 0]
    if not out:
        raise ValueError("nothing left of that image once its background is taken away")
    return out
