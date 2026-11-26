"""World Drive's current mark, traced into flat printable colours.

    pip install opencv-python-headless      # only this script needs it
    python3 worlddrive/trace_mark.py

The site's mark (art/mark_source.png: Neptune-digital-twin's
exports/worlddrive-mark-transparent.png, 1024 px) is a painted logo: a shaded
globe with lighter continents, a yellow road running down the front of it in an
S, a car coming toward you on it, and a yellow orbit ring round the back. This
turns it into four flat colours, the four filaments the coasters print with,
and writes art/mark_logo.svg for designs.py (the coaster) and, as separate
pieces made printable at keychain size, art/mark_logo_keychain.json (the relief
keychain, whose pieces stand at heights of their own):

    navy        the body: outlines, the lane dashes, the car
    blue        the ocean
    yellow      the road and the orbit ring
    light blue  the continents, and the car's windows and headlights

The ocean is taken as the globe's whole circle less the road, so its painted
shading (a gloss at the top, dark toward the bottom) doesn't matter; the
continents are what's lighter than the ocean round them, found against the
ocean's own shading (a grey opening wider than any continent). Anything
narrower than MIN_WIDTH mm at the coaster's size is dropped, so every piece
prints with a 0.4 mm nozzle.
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely import affinity
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "art" / "mark_source.png"
OUT = HERE / "art" / "mark_logo.svg"
PIECES = HERE / "art" / "mark_logo_keychain.json"

NAVY, BLUE, YELLOW, LIGHT = "#0b1424", "#2b7de0", "#ffd23f", "#8cc4ff"
UNITS = 100.0          # the art's width, in designs.py's units (~ the coaster's mm)
COASTER = 110.0        # the coaster it's made for, mm wide
KEYCHAIN = 55.0        # and the relief keychain
MIN_WIDTH = 0.6        # mm: narrower than this is dropped
GAP = 0.9              # mm of navy between the road and the globe
CONTINENT = 22         # how much lighter than the ocean a continent is (0-255)
OPENING = 181          # px: wider than any continent


def masks(path=SOURCE):
    im = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    r, g, b, a = (im[..., i] for i in range(4))
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    solid = a > 128
    yellow = solid & (r > 170) & (g > 120) & (b < 110) & (r - b > 100)
    white = solid & (r > 185) & (g > 185) & (b > 185) & (np.abs(r - b) < 70)
    blue = solid & ~yellow & ~white & (b > 83) & (b - r > 40)
    # the ocean's shading, with the continents opened out of it
    flat = np.where(blue, lum, 255).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (OPENING, OPENING))
    shade = cv2.GaussianBlur(cv2.dilate(cv2.erode(flat, k), k).astype(np.float32), (0, 0), 15)
    land = blue & (lum - shade > CONTINENT)
    # the globe: the smallest circle round its blue
    pts = np.argwhere(blue)[:, ::-1].astype(np.float32)
    (cx, cy), rad = cv2.minEnclosingCircle(pts)
    return dict(yellow=yellow, white=white, land=land, globe=(cx, cy, rad), size=im.shape[:2])


def polygons(mask):
    """A boolean mask as shapely polygons (pixel units, y down)."""
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    if hier is None:
        return unary_union([])
    for i, c in enumerate(contours):
        if hier[0][i][3] != -1 or len(c) < 4:
            continue
        holes = [contours[j][:, 0, :] for j in range(len(contours))
                 if hier[0][j][3] == i and len(contours[j]) >= 4]
        out.append(make_valid(Polygon(c[:, 0, :], holes)).buffer(0))
    return unary_union(out)


def printable(g, width):
    """Only what's at least `width` across survives, smoothed a little."""
    g = g.buffer(-width / 2).buffer(width / 2)
    # and no island or lake under about twice that across
    polys = []
    for p in getattr(g, "geoms", [g]):
        if p.geom_type != "Polygon" or p.area <= 4 * width ** 2:
            continue
        polys.append(Polygon(p.exterior, [r for r in p.interiors if Polygon(r).area > 4 * width ** 2]))
    return unary_union(polys).simplify(0.05)


def pieces(size=None):
    """The mark's pieces, in art units (about 100 wide, y up), made printable for a part
    `size` mm wide: {ocean, land, road, car, glass}. The car is its whole shape (the body, and
    the windows and headlights in it); glass is just the windows and headlights."""
    size = size or COASTER
    m = masks()
    h, w = m["size"]
    px = UNITS / w                      # art units per pixel
    mm = size / UNITS                   # mm per art unit
    to_art = lambda g: affinity.scale(g, px, -px, origin=(0, 0))

    road = to_art(polygons(m["yellow"]))
    road_filled = unary_union([Polygon(p.exterior) for p in getattr(road, "geoms", [road])])
    # what the road goes round: the lane dashes, and the car, the biggest of them
    inside = [p for p in getattr(road_filled.difference(road), "geoms", [])] or [road_filled.difference(road)]
    car = max(inside, key=lambda p: p.area)
    glass = to_art(polygons(m["white"])).intersection(road_filled)
    land = to_art(polygons(m["land"]))
    cx, cy, rad = m["globe"]
    globe = to_art(Point(cx, cy).buffer(rad - 2, 256))

    ocean_all = globe.difference(road_filled.buffer(GAP / mm))
    width = MIN_WIDTH / mm
    # The globe is all ocean or land, nothing between: land too thin to print goes back to the
    # ocean, and a strait too thin to print goes to the land, so no piece of either is narrower
    # than MIN_WIDTH and no navy shows through on the globe's top.
    land = printable(land.intersection(ocean_all), width)
    ocean = printable(ocean_all.difference(land), width)
    land = ocean_all.difference(ocean).buffer(-width * 0.25).buffer(width * 0.25)
    return dict(ocean=ocean, land=printable(land, width), road=printable(road.difference(glass.buffer(0.2)), width),
                car=printable(car, width), glass=printable(glass, width))


def trace():
    """The coaster's four flat colours: {colour: geometry}."""
    p = pieces(COASTER)
    return {BLUE: p["ocean"], LIGHT: unary_union([p["land"], p["glass"]]), YELLOW: p["road"]}


def write_pieces(size=KEYCHAIN, path=PIECES):
    """The pieces for a part `size` mm wide, as WKT in JSON, for designs.py's relief keychain."""
    import json
    Path(path).write_text(json.dumps({k: v.wkt for k, v in pieces(size).items()}))


def write_svg(layers, path=OUT, pad=2.0):
    allg = unary_union(list(layers.values()))
    x0, y0, x1, y1 = allg.bounds
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    H = y1 - y0

    def ring(c):
        pts = np.asarray(c.coords)
        return "M" + "L".join(f"{x - x0:.3f},{H - (y - y0):.3f}" for x, y in pts) + "Z"

    paths = []
    for colour, g in layers.items():
        for p in getattr(g, "geoms", [g]):
            if p.is_empty or p.geom_type != "Polygon":
                continue
            d = ring(p.exterior) + "".join(ring(i) for i in p.interiors)
            paths.append(f'<path fill="{colour}" fill-rule="evenodd" d="{d}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {x1 - x0:.3f} {H:.3f}">'
           + "".join(paths) + "</svg>")
    Path(path).write_text(svg)
    return svg


if __name__ == "__main__":
    layers = trace()
    write_svg(layers)
    for colour, g in layers.items():
        print(colour, f"{g.area:.0f} units², {len(getattr(g, 'geoms', [g]))} pieces")
    print("wrote", OUT)
    write_pieces()
    print("wrote", PIECES)
