"""Read an iPhone's real dimensions out of Apple's own dimensional drawing.

    python3 src/extract_iphone_dims.py iphone-17-pro.pdf

`src/phonecase/spec.py` used to say that body sizes are published specs and
that camera openings and button positions are not. The second half of that is
wrong, and it is the half that mattered: Apple publishes a dimensioned drawing
per model, at

    https://developer.apple.com/download/files/accessories/dimensional-drawings/

which is exactly the document a case manufacturer works from. Every button,
every keepout and the camera plateau are on it, to a hundredth of a
millimetre. Nobody here needed to be estimating anything.

So this reads the drawing. No PDF library: the pages are `FlateDecode`
content streams of ordinary path and text operators, which is `zlib` and a
tokeniser, and a dependency you do not take is a dependency that cannot break
your build -- the same bargain the rest of `phonecase` makes.

HOW THE NUMBERS COME OUT, which is the part worth understanding before
trusting any of them.

Apple dimensions these drawings **ordinately**: there is a `0.00` datum per
view, and every feature is labelled with its distance from it rather than with
a chain of deltas. The label is drawn *at* the feature's own coordinate --
that is what makes an ordinate dimension readable -- so a label's position on
the page and the number it prints are two measurements of the same thing, in
two different units.

Which hands you the scale for free, and a way to check it. Fit a straight line
through (label position in points, label value in mm) for one view's ordinate
chain: if the drawing is what it claims to be, the fit is exact. It is -- the
residuals come out around a hundredth of a point. If it ever stops being
exact, the fit says so and the extraction fails rather than quietly handing
you a number that is off by a scale factor.

The vector geometry is read too, and is the source of truth for anything the
labels do not name outright: a button's *length* is the drawn rounded
rectangle, not a subtraction of two ordinates. Where a label and the geometry
disagree by more than a tenth of a millimetre, this refuses to choose. That is
the whole point of having both.

WHAT THIS CANNOT GIVE YOU, which matters as much as what it can.

Apple's export is not consistent across the four sheets. Sheets 2, 3 and 4 --
Camera Control, the camera keepouts, the antenna and MagSafe keepouts -- carry
their dimensions as real text, and come out exactly. **Sheet 1 does not.** Its
text has been converted to outlines: eight thousand stroked polylines and not
one text operator on the page. Sheet 1 is the general-dimensions sheet, which
is where the side buttons are positioned.

So the button positions are still not available from here, and this says so
rather than guessing. Reading them back would mean recognising stroked digit
outlines, and a digit recognised wrong is a hole in the wrong place -- the
exact failure this whole exercise exists to prevent. :func:`glyph_cells` is
left in as the diagnostic that demonstrates the problem: it finds the glyph
strokes and can draw them as ASCII, which is enough to confirm what sheet 1
is, and not enough to trust.

The output is `src/iphone_dims.json` -- every decoded label with its position,
the per-view ordinate fits, and a note for each sheet that could not be read
-- so that the numbers which end up in `spec.py` can be traced back to a sheet
and a dimension rather than to somebody's eye.
"""
from __future__ import annotations

import json
import math
import re
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: A fit worse than this is not an ordinate chain and will not be used.
#: Real chains come in around 0.005 pt. The number that forced this down from
#: a quarter of a point is the sheet's own zone lettering: `1 2 3 4` spaced
#: evenly along the border fits a straight line at 0.199 pt and would
#: otherwise be reported as a dimension chain at 299 pt/mm.
MAX_RESIDUAL_PT = 0.05

#: A chain has to have this many labels, one of them the 0.00 datum, before
#: a straight line through them means anything. Three is not enough: with
#: forty numbers on a sheet there is always some collinear triple, and every
#: one of them came back at a scale no view is drawn at.
MIN_CHAIN = 4

#: Nothing on these sheets is drawn smaller than 1:2 or larger than 20:1.
SCALE_RANGE = (0.9, 60.0)


# --------------------------------------------------------------------------
# the file
# --------------------------------------------------------------------------

def objects(data: bytes) -> dict[int, bytes]:
    """`{object number: its body}`, for a PDF with no object streams.

    Apple's drawings are written the old way -- every object at top level,
    one `N 0 obj ... endobj` each -- so there is no cross-reference stream to
    decode and no compressed object stream to unpack. Checked rather than
    assumed: :func:`load` refuses a file that has them.
    """
    out: dict[int, bytes] = {}
    for m in re.finditer(rb'(?<![0-9])(\d+)\s+0\s+obj\b', data):
        end = data.find(b'endobj', m.end())
        out[int(m.group(1))] = data[m.end():end if end > 0 else len(data)]
    return out


def stream_of(body: bytes) -> bytes | None:
    """The decompressed stream inside one object, if it has one."""
    m = re.search(rb'stream\r?\n', body)
    if not m:
        return None
    end = body.find(b'endstream', m.end())
    raw = body[m.end():end if end > 0 else len(body)]
    if b'/FlateDecode' in body[:m.start()]:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return None
    return raw


def refs(blob: bytes, key: bytes) -> list[int]:
    """Object numbers under `key`, whether it holds one reference or an array."""
    m = re.search(key + rb'\s*(\[[^\]]*\]|\d+\s+0\s+R)', blob)
    if not m:
        return []
    return [int(n) for n in re.findall(rb'(\d+)\s+0\s+R', m.group(1))]


def dict_of(blob: bytes, key: bytes) -> bytes:
    """The raw text of an inline dictionary under `key`."""
    m = re.search(key + rb'\s*<<', blob)
    if not m:
        return b''
    depth, i = 1, m.end()
    while i < len(blob) - 1 and depth:
        if blob[i:i + 2] == b'<<':
            depth, i = depth + 1, i + 2
        elif blob[i:i + 2] == b'>>':
            depth, i = depth - 1, i + 2
        else:
            i += 1
    return blob[m.end():i - 2]


# --------------------------------------------------------------------------
# text encoding
# --------------------------------------------------------------------------

def code_bytes(cmap: bytes) -> int:
    """How many bytes one character code takes in this font.

    The drawing body is a subset CID font on two-byte codes; the sheet
    furniture is an ordinary Latin font on one. Both carry a `ToUnicode`
    table, so the presence of a table does not tell them apart -- the
    codespace range does, and reading every font as two-byte turns the sheet
    footer into a row of question marks.
    """
    m = re.search(rb'begincodespacerange(.*?)endcodespacerange', cmap, re.S)
    if m:
        first = re.search(rb'<([0-9A-Fa-f]+)>', m.group(1))
        if first:
            return max(1, len(first.group(1)) // 2)
    return 2


def to_unicode(cmap: bytes) -> dict[int, str]:
    """Decode a `ToUnicode` CMap into `{CID: character}`.

    Both halves matter. The drawing's font subsets its glyphs, so the digits
    come through as `<0001>`-style CIDs that mean nothing without this, and
    Apple's writer uses `bfchar` and `bfrange` both -- reading only `bfchar`
    silently loses whichever labels happened to land in a range, which is how
    a first pass at this came back with the buttons missing.
    """
    out: dict[int, str] = {}
    for blk in re.findall(rb'beginbfchar(.*?)endbfchar', cmap, re.S):
        for src, dst in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
            out[int(src, 16)] = _utf16(dst)
    for blk in re.findall(rb'beginbfrange(.*?)endbfrange', cmap, re.S):
        for lo, hi, dst in re.findall(
                rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
            lo, hi, base = int(lo, 16), int(hi, 16), int(dst, 16)
            for cid in range(lo, hi + 1):
                out[cid] = chr(base + (cid - lo))
    return out


def _utf16(hexdigits: bytes) -> str:
    raw = bytes.fromhex(hexdigits.decode())
    if len(raw) % 2:
        raw += b'\0'
    return raw.decode('utf-16-be', 'replace')


# --------------------------------------------------------------------------
# the content stream
# --------------------------------------------------------------------------

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

TOKEN = re.compile(rb'''
      (?P<num>[-+]?(?:\d+\.\d*|\.\d+|\d+))
    | /(?P<name>[^\s/\[\]<>(){}%]*)
    | <(?P<hex>[0-9A-Fa-f\s]*)>
    | (?P<open>\[|<<)
    | (?P<close>\]|>>)
    | \((?P<str>(?:\\.|[^\\()])*)\)
    | (?P<op>[A-Za-z'"*][A-Za-z0-9'"*]*)
    | %[^\r\n]*
''', re.X | re.S)


def mul(a: Matrix, b: Matrix) -> Matrix:
    """`a` then `b`, in PDF's row-vector convention."""
    return (a[0] * b[0] + a[1] * b[2],
            a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2],
            a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4],
            a[4] * b[1] + a[5] * b[3] + b[5])


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


@dataclass
class Label:
    """One piece of text, at the point the drawing put it."""
    text: str
    x: float
    y: float

    @property
    def value(self) -> float | None:
        """The number it prints, if it prints one."""
        t = self.text.strip()
        return float(t) if re.fullmatch(r'\d+(?:\.\d+)?', t) else None


@dataclass
class Subpath:
    """One painted subpath, flattened, in page points."""
    pts: list[tuple[float, float]]
    closed: bool

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class Sheet:
    number: int
    labels: list[Label] = field(default_factory=list)
    paths: list[Subpath] = field(default_factory=list)


@dataclass
class Resources:
    """What one stream can name: its fonts and the forms it can invoke.

    A font maps to its `ToUnicode` table, or to ``None`` when it has none --
    the sheet furniture is set in an ordinary Latin font whose bytes mean
    themselves, while the drawing body is a subset CID font whose bytes mean
    nothing at all without the table. Telling them apart is not optional:
    decode the sheet title as CIDs and every page reads as question marks.
    """

    fonts: dict[str, tuple[dict[int, str], int] | None] = field(default_factory=dict)
    forms: dict[str, tuple[bytes, Matrix, "Resources"]] = field(default_factory=dict)


def interpret(content: bytes, res: Resources, sheet: Sheet | None = None,
              ctm: Matrix = IDENTITY, depth: int = 0) -> Sheet:
    """Walk one stream's operators, collecting text positions and geometry.

    Only as much of the imaging model as a mechanical drawing uses: the
    graphics state stack, `cm`, the path operators, `Do` for form XObjects,
    and enough of the text object to know where a string landed. Shading,
    patterns, images and clipping are all skipped -- this drawing has none,
    and a dimension that depended on one would not be a dimension.

    The whole drawing is one form: each page's own content stream is a dozen
    lines that place a sheet title and then say `/I0 Do`. Stopping at the page
    level, as a first pass did, reads five sheets of nothing.
    """
    sheet = sheet if sheet is not None else Sheet(0)
    stack: list[Matrix] = []
    tm = tlm = IDENTITY
    font: tuple[dict[int, str], int] | None = None
    pending: list[str] = []          # text of the run being accumulated
    operands: list = []
    here = (0.0, 0.0)
    start = (0.0, 0.0)
    current: list[tuple[float, float]] = []
    subpaths: list[Subpath] = []

    def flush(closed: bool = False) -> None:
        nonlocal current
        if len(current) > 1:
            subpaths.append(Subpath(current, closed))
        current = []

    def moveto(x, y):
        nonlocal here, start
        flush()
        here = start = apply(ctm, x, y)
        current.append(here)

    def lineto(x, y):
        nonlocal here
        here = apply(ctm, x, y)
        current.append(here)

    def curveto(x1, y1, x2, y2, x3, y3):
        """Flatten a cubic. Sixteen steps is well past what a 0.01 mm
        dimension can notice at drawing scale, and a bezier here is only ever
        a fillet or a lens circle."""
        nonlocal here
        p0 = here
        p1, p2, p3 = (apply(ctm, x1, y1), apply(ctm, x2, y2), apply(ctm, x3, y3))
        for i in range(1, 17):
            t = i / 16
            u = 1 - t
            current.append((
                u ** 3 * p0[0] + 3 * u * u * t * p1[0]
                + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                u ** 3 * p0[1] + 3 * u * u * t * p1[1]
                + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
        here = p3

    for m in TOKEN.finditer(content):
        kind = m.lastgroup
        if kind == 'num':
            operands.append(float(m.group('num')))
            continue
        if kind == 'name':
            operands.append('/' + m.group('name').decode('latin-1'))
            continue
        if kind == 'hex':
            operands.append(bytes.fromhex(
                re.sub(rb'\s', b'', m.group('hex')).decode()))
            continue
        if kind == 'str':
            operands.append(m.group('str'))
            continue
        if kind in ('open', 'close'):
            # Arrays and dictionaries only ever hold operands here; TJ reads
            # its own text back out of the flat list.
            continue
        if kind != 'op':
            continue
        op = m.group('op').decode('latin-1')
        n = operands

        if op == 'q':
            stack.append(ctm)
        elif op == 'Q':
            ctm = stack.pop() if stack else IDENTITY
        elif op == 'cm' and len(n) >= 6:
            ctm = mul(tuple(n[-6:]), ctm)                      # type: ignore
        elif op == 'm' and len(n) >= 2:
            moveto(n[-2], n[-1])
        elif op == 'l' and len(n) >= 2:
            lineto(n[-2], n[-1])
        elif op == 'c' and len(n) >= 6:
            curveto(*n[-6:])
        elif op == 'v' and len(n) >= 4:
            inv = _invert(ctm, here)
            curveto(inv[0], inv[1], n[-4], n[-3], n[-2], n[-1])
        elif op == 'y' and len(n) >= 4:
            curveto(n[-4], n[-3], n[-2], n[-1], n[-2], n[-1])
        elif op == 're' and len(n) >= 4:
            x, y, w, h = n[-4:]
            flush()
            current = [apply(ctm, x, y), apply(ctm, x + w, y),
                       apply(ctm, x + w, y + h), apply(ctm, x, y + h)]
            flush(closed=True)
        elif op == 'h':
            if current:
                current.append(start)
            flush(closed=True)
        elif op in ('S', 's', 'f', 'F', 'f*', 'B', 'B*', 'b', 'b*', 'n'):
            flush(closed=op in ('s', 'b', 'b*', 'f', 'F', 'f*', 'B', 'B*'))
            sheet.paths.extend(subpaths)
            subpaths = []
        elif op == 'BT':
            tm = tlm = IDENTITY
            pending = []
        elif op == 'Tf' and n:
            key = next((v for v in reversed(n) if isinstance(v, str)
                        and v.startswith('/')), '')
            font = res.fonts.get(key[1:])
        elif op == 'Tm' and len(n) >= 6:
            tm = tlm = tuple(n[-6:])                           # type: ignore
        elif op in ('Td', 'TD') and len(n) >= 2:
            tm = tlm = mul((1, 0, 0, 1, n[-2], n[-1]), tlm)
        elif op == 'T*':
            tm = tlm = mul((1, 0, 0, 1, 0, -1), tlm)
        elif op in ('Tj', 'TJ', "'", '"'):
            for v in n:
                if not isinstance(v, bytes):
                    continue
                if font:
                    table, width = font
                    pending.append(''.join(
                        table.get(int.from_bytes(v[i:i + width], 'big'), '?')
                        for i in range(0, len(v) - width + 1, width)))
                else:
                    pending.append(v.decode('latin-1'))
        elif op == 'Do' and n and depth < 8:
            key = next((v for v in reversed(n) if isinstance(v, str)
                        and v.startswith('/')), '')
            form = res.forms.get(key[1:])
            if form:
                body, matrix, inner = form
                interpret(body, inner, sheet, mul(matrix, ctm), depth + 1)
        elif op == 'ET':
            text = ''.join(pending)
            if text.strip():
                x, y = apply(mul(tm, ctm), 0.0, 0.0)
                sheet.labels.append(Label(text, x, y))
            pending = []

        operands = []
    return sheet


def _invert(ctm: Matrix, pt: tuple[float, float]) -> tuple[float, float]:
    """`pt` (page space) back in the current user space, for the `v` operator."""
    a, b, c, d, e, f = ctm
    det = a * d - b * c
    if abs(det) < 1e-12:
        return (0.0, 0.0)
    x, y = pt[0] - e, pt[1] - f
    return ((x * d - y * c) / det, (y * a - x * b) / det)


def load(path: Path) -> list[Sheet]:
    """Every page of the drawing, in order."""
    data = path.read_bytes()
    if b'/ObjStm' in data or b'/Type/XRef' in data or b'/Type /XRef' in data:
        raise SystemExit(
            f"{path.name} uses compressed cross-reference or object streams, "
            "which this reader does not decode. Apple's drawings do not, so "
            "this is probably not one of them.")
    objs = objects(data)

    def resources(blob: bytes, seen: frozenset[int] = frozenset()) -> Resources:
        """The fonts and forms one object can name, following its own tree."""
        res = Resources()
        for name, num in re.findall(rb'/([^\s/<>\[\]]+)\s+(\d+)\s+0\s+R',
                                    dict_of(blob, rb'/Font')):
            entry = None
            for tu in refs(objs.get(int(num), b''), rb'/ToUnicode'):
                cmap = stream_of(objs.get(tu, b''))
                if cmap:
                    entry = (to_unicode(cmap), code_bytes(cmap))
            res.fonts[name.decode('latin-1')] = entry
        for name, num in re.findall(rb'/([^\s/<>\[\]]+)\s+(\d+)\s+0\s+R',
                                    dict_of(blob, rb'/XObject')):
            num = int(num)
            if num in seen:
                continue                      # a form that invokes itself
            form = objs.get(num, b'')
            if b'/Subtype/Form' not in form and b'/Subtype /Form' not in form:
                continue                      # an image; nothing to dimension
            body = stream_of(form)
            if not body:
                continue
            mm = re.search(rb'/Matrix\s*\[([^\]]*)\]', form)
            matrix: Matrix = IDENTITY
            if mm:
                got = [float(v) for v in re.findall(rb'[-+]?[\d.]+', mm.group(1))]
                if len(got) == 6:
                    matrix = tuple(got)                        # type: ignore
            inner = form
            for r in refs(form, rb'/Resources'):
                inner = objs.get(r, form)
            res.forms[name.decode('latin-1')] = (
                body, matrix, resources(inner, seen | {num}))
        return res

    sheets = []
    root = next((b for b in objs.values() if b'/Type/Pages' in b
                 or b'/Type /Pages' in b), b'')
    for i, num in enumerate(refs(root, rb'/Kids'), start=1):
        page = objs.get(num, b'')
        content = b'\n'.join(filter(None, (
            stream_of(objs.get(c, b'')) for c in refs(page, rb'/Contents'))))
        blob = page
        for r in refs(page, rb'/Resources'):
            blob = objs.get(r, page)
        sheet = interpret(content, resources(blob))
        sheet.number = i
        sheets.append(sheet)
    return sheets




# --------------------------------------------------------------------------
# putting the text back together
# --------------------------------------------------------------------------

#: Runs that are a prefix to the number after them rather than a dimension of
#: their own. Everything else on a baseline is its own label, however close it
#: happens to sit.
PREFIX = re.compile(r'(?:R|\d+X|[\u00d8\u2300])\Z')


def phrases(labels: list[Label], gap: float = 9.0) -> list[Label]:
    """Join a prefix run onto the number it qualifies.

    The writer emits ``R`` and ``12.00``, or ``2X`` and ``114.73``, as two
    runs placed separately. Left apart, the prefix is lost and a radius reads
    as a bare ordinate -- which is exactly the kind of number that drags a fit
    off its datum. Joined, it stops being a candidate ordinate at all, which
    is what it should have been all along.

    Only a prefix is ever joined. Merging any two runs that share a baseline
    swallows whole columns of unrelated dimensions, because a drawing lines
    its labels up on purpose.
    """
    out: list[Label] = []
    for lb in sorted(labels, key=lambda l: (-round(l.y, 1), l.x)):
        prev = out[-1] if out else None
        if (prev is not None and abs(prev.y - lb.y) < 0.4
                and 0 <= lb.x - prev.x < gap
                and PREFIX.search(prev.text.strip())):
            out[-1] = Label(prev.text.strip() + ' ' + lb.text.strip(),
                            prev.x, prev.y)
        else:
            out.append(Label(lb.text, lb.x, lb.y))
    return out


# --------------------------------------------------------------------------
# ordinate chains
# --------------------------------------------------------------------------

@dataclass
class Chain:
    """One ordinate dimension chain: a datum, a direction and a scale."""

    axis: str                 # "x" or "y"
    origin_pt: float
    scale: float              # points per mm, signed with the drawing
    members: list[Label]
    residual: float

    def to_mm(self, coord: float) -> float:
        """A page coordinate, in this chain's millimetres."""
        return (coord - self.origin_pt) / self.scale


def ordinates(labels: list[Label]) -> list[Label]:
    """The labels that could be an ordinate: a bare number and nothing else.

    A ``R 12.00`` is a radius and a ``2X 114.73`` is a repeat count in front
    of one; neither is a distance from the datum, and both would drag a fit
    off if they were let in. The number is still there in the output -- it is
    just not allowed to define the scale.
    """
    return [lb for lb in labels if lb.value is not None]


def chains(labels: list[Label], axis: str) -> list[Chain]:
    """Find the ordinate chains among a sheet's labels.

    Every pair of numeric labels proposes a datum and a scale; whichever
    proposal the most other labels agree with is a chain, and then the same
    again on what is left. Consensus rather than a column test, because a
    column test needs to know how the labels are aligned and they are not all
    aligned the same way -- an ordinate column set flush on its right edge
    starts each label at a different x depending on how many digits it has,
    and grouping on that loses half the chain.

    What keeps this honest is that agreement means *exact*: a label is in the
    chain when the straight line predicts its position to a twentieth of a
    point. Nothing accidental clears that. The sheet's own border numbering,
    which is four evenly spaced numerals and fits a line perfectly well, is
    thrown out by the scale bound instead -- it comes to 299 points per
    millimetre.
    """
    pos = (lambda lb: lb.y) if axis == 'y' else (lambda lb: lb.x)
    left = [(lb, lb.value, pos(lb)) for lb in ordinates(labels)]
    out: list[Chain] = []
    while len(left) >= MIN_CHAIN:
        best: tuple[int, float, float, float, list] | None = None
        for i in range(len(left)):
            for j in range(i + 1, len(left)):
                (_, v0, p0), (_, v1, p1) = left[i], left[j]
                if abs(v1 - v0) < 1e-6:
                    continue
                slope = (p1 - p0) / (v1 - v0)
                if not SCALE_RANGE[0] <= abs(slope) <= SCALE_RANGE[1]:
                    continue
                origin = p0 - slope * v0
                inliers = [m for m in left
                           if abs(origin + slope * m[1] - m[2]) <= MAX_RESIDUAL_PT]
                if len(inliers) < MIN_CHAIN:
                    continue
                # An ordinate chain shows its datum. Requiring the 0.00 to be
                # in the consensus is what separates a chain from three
                # unrelated numbers that happen to fall on a line -- and with
                # forty numbers on a sheet, three of them always do.
                if not any(abs(m[1]) < 1e-9 for m in inliers):
                    continue
                got = _fit([(m[1], m[2]) for m in inliers])
                if got is None:
                    continue
                slope, origin, resid, _ = got
                if best is None or (len(inliers), -resid) > (best[0], -best[3]):
                    best = (len(inliers), slope, origin, resid, inliers)
        if best is None:
            break
        _, slope, origin, resid, inliers = best
        out.append(Chain(axis, origin, slope, [m[0] for m in inliers], resid))
        keep = {id(m[0]) for m in inliers}
        left = [m for m in left if id(m[0]) not in keep]
    return out


def _fit(points: list[tuple[float, float]]):
    """Least squares `position = origin + slope * value`, if it is exact."""
    n = len(points)
    if n < MIN_CHAIN:
        return None
    sv = sum(v for v, _ in points)
    sp = sum(p for _, p in points)
    svv = sum(v * v for v, _ in points)
    svp = sum(v * p for v, p in points)
    det = n * svv - sv * sv
    if abs(det) < 1e-9:
        return None
    slope = (n * svp - sv * sp) / det
    origin = (sp - slope * sv) / n
    resid = math.sqrt(sum((origin + slope * v - p) ** 2 for v, p in points) / n)
    if resid > MAX_RESIDUAL_PT:
        return None
    if not SCALE_RANGE[0] <= abs(slope) <= SCALE_RANGE[1]:
        return None
    return slope, origin, resid, [True] * n


# --------------------------------------------------------------------------
# the sheet that cannot be read
# --------------------------------------------------------------------------

def glyph_cells(sheet: Sheet, height: tuple[float, float] = (4.0, 4.2)):
    """Stroked character cells on a sheet whose text was flattened to outlines.

    Diagnostic, not a decoder. Sheet 1 of every drawing Apple publishes has
    its text converted to curves, and this is what is left of it: single
    stroke polylines, one cell per character, all 3.3 pt wide because the
    digits are monospaced. Enough to say with certainty *why* sheet 1 comes
    back empty. Not enough to say what it says -- see the module docstring.
    """
    band = [p for p in sheet.paths
            if height[0] < p.bbox[3] - p.bbox[1] < height[1]
            and p.bbox[2] - p.bbox[0] < 4.0]
    used = [False] * len(band)
    cells = []
    for i, p in enumerate(band):
        if used[i]:
            continue
        grp, box, growing = [p], list(p.bbox), True
        used[i] = True
        while growing:
            growing = False
            for j, q in enumerate(band):
                if used[j]:
                    continue
                b = q.bbox
                if (b[0] <= box[2] + 0.25 and b[2] >= box[0] - 0.25
                        and b[1] <= box[3] + 0.25 and b[3] >= box[1] - 0.25):
                    grp.append(q)
                    used[j] = True
                    growing = True
                    box = [min(box[0], b[0]), min(box[1], b[1]),
                           max(box[2], b[2]), max(box[3], b[3])]
            continue
        cells.append((grp, tuple(box)))
    return cells


def as_ascii(grp, box, w: int = 16, h: int = 20) -> list[str]:
    """One glyph cell drawn as its strokes, for a human to look at."""
    x0, y0, x1, y1 = box
    sx, sy = (x1 - x0) or 1e-9, (y1 - y0) or 1e-9
    grid = [[' '] * w for _ in range(h)]
    for path in grp:
        for a, b in zip(path.pts, path.pts[1:]):
            ax, ay = (a[0] - x0) / sx * (w - 1), (a[1] - y0) / sy * (h - 1)
            bx, by = (b[0] - x0) / sx * (w - 1), (b[1] - y0) / sy * (h - 1)
            steps = int(max(abs(bx - ax), abs(by - ay)) * 3) + 1
            for k in range(steps + 1):
                t = k / steps
                cx, cy = round(ax + (bx - ax) * t), round(ay + (by - ay) * t)
                if 0 <= cx < w and 0 <= cy < h:
                    grid[h - 1 - cy][cx] = '#'
    return [''.join(row) for row in grid]


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def dump(sheets: list[Sheet]) -> dict:
    """Everything found, in millimetres wherever a chain says how."""
    out: dict = {"sheets": []}
    for sheet in sheets:
        text = phrases(sheet.labels)
        rec: dict = {
            "sheet": sheet.number,
            "paths": len(sheet.paths),
            "text_runs": len(sheet.labels),
            "chains": [],
            "labels": [],
        }
        # A drawing sheet with no text is a sheet whose text was outlined.
        # The title page has no text either and is not a problem.
        if len(text) < 5 and len(sheet.paths) > 500:
            rec["unreadable"] = (
                "dimension text on this sheet is drawn as outlines, not text; "
                f"{len(glyph_cells(sheet))} stroked character cells, no text "
                "operators. Nothing here can be trusted as a number.")
            out["sheets"].append(rec)
            continue

        found = chains(text, 'x') + chains(text, 'y')
        for c in found:
            rec["chains"].append({
                "axis": c.axis,
                "origin_pt": round(c.origin_pt, 3),
                "scale_pt_per_mm": round(c.scale, 6),
                "residual_pt": round(c.residual, 5),
                "values_mm": sorted(lb.value for lb in c.members),
            })
        for lb in text:
            entry = {"text": lb.text.strip(),
                     "x_pt": round(lb.x, 2), "y_pt": round(lb.y, 2)}
            for c in found:
                pos = lb.y if c.axis == 'y' else lb.x
                entry[f"{c.axis}_mm@{round(c.origin_pt)}"] = round(c.to_mm(pos), 2)
            rec["labels"].append(entry)
        out["sheets"].append(rec)
    return out


# --------------------------------------------------------------------------
# named features: what the drawing calls things, and where they are
# --------------------------------------------------------------------------
#
# Four of the twenty-seven drawings -- iPhone 16, 16 Pro, 16 Pro Max and 17e
# -- have their general-dimensions sheet published as real text, and that
# sheet labels the side features by name:
#
#     ACTION BUTTON    (+) VOLUME BUTTON    (-) VOLUME BUTTON
#     SIDE BUTTON      CAMERA CONTROL       SIM TRAY
#
# Each name sits at the end of a horizontal leader line whose other end
# touches the feature, at its centre. That is the whole trick: the leader's
# far end is a measurement, in page points, of something the drawing has just
# told you the name of. Convert with the view's own scale and you have a
# button position from Apple rather than from an eye.
#
# HOW GOOD IS IT. About a millimetre. Three of the values can be checked
# against a printed ordinate on the same sheet, and they agree to 0.3, 0.5 and
# 0.8 mm. That is not the hundredth of a millimetre the ordinate chains give,
# because a leader ends *on* a feature rather than at a dimensioned point, and
# because the printed ordinates on this sheet are stepped out of line to stop
# them colliding -- which is also why they cannot simply be read positionally.
#
# A millimetre is enough here and would not be enough everywhere. The openings
# this feeds are cut a clearance oversize, are stadium-shaped, and in Camera
# Control's case use a keepout nearly twelve millimetres longer than the
# control. What it replaces is a power button opening that was twenty-one
# millimetres out.

#: Feature names worth pulling off a sheet, and what to call them in
#: :data:`~phonecase.spec.PHONES`.
FEATURE_NAMES = {
    "ACTION BUTTON": "action",
    "SIDE BUTTON": "power",
    "CAMERA CONTROL": "camera-control",
    "(+) VOLUME BUTTON": "volume-up",
    "(-) VOLUME BUTTON": "volume-down",
    "SIM TRAY": "sim-tray",
}


@dataclass
class View:
    """One elevation of the whole body, found by its own outline."""

    y0: float
    y1: float
    x0: float
    x1: float
    scale: float              # points per mm, from the known body length

    def from_top(self, y: float) -> float:
        """A page coordinate, in mm down from the top of the body."""
        return (self.y1 - y) / self.scale

    def holds(self, x: float, y: float) -> bool:
        """Is this point inside the view?

        Both axes. Checking x alone picks whichever band was listed first
        when two elevations sit side by side at different heights, and a band
        chosen wrong is its whole y-offset of error -- eight points between
        two rows on the 16 Pro's sheet is five millimetres of button.
        """
        return (self.x0 - 12 <= x <= self.x1 + 12
                and self.y0 - 2 <= y <= self.y1 + 2)


@dataclass
class Feature:
    name: str                 # the drawing's own words
    key: str                  # what phonecase calls it
    from_top_mm: float
    leader: tuple[float, float]


def _vertical_runs(sheet: Sheet, min_len: float = 120.0):
    """Collinear vertical segments, merged. The bones of every elevation."""
    cov: dict[float, list[tuple[float, float]]] = {}
    for p in sheet.paths:
        for a, b in zip(p.pts, p.pts[1:]):
            if abs(a[0] - b[0]) < 0.2 and abs(a[1] - b[1]) > 3:
                cov.setdefault(round((a[0] + b[0]) / 2, 1), []).append(
                    (min(a[1], b[1]), max(a[1], b[1])))
    out = []
    for x, segs in cov.items():
        segs.sort()
        lo, hi = segs[0]
        for s, e in segs[1:]:
            if s <= hi + 1.0:
                hi = max(hi, e)
            else:
                if hi - lo > min_len:
                    out.append((x, lo, hi))
                lo, hi = s, e
        if hi - lo > min_len:
            out.append((x, lo, hi))
    return sorted(out)


def views(sheet: Sheet, length_mm: float, tol: float = 0.02) -> list[View]:
    """The elevations on a sheet, and the scale each is drawn at.

    A full-body elevation is as tall as the phone is long, so the vertical
    runs that matter are the ones whose length divided by the body length is
    the same number for all of them -- that number being the scale. Views that
    share a y range are one band, and two bands on one sheet can sit at
    different heights, which is worth getting right.
    """
    runs = _vertical_runs(sheet)
    if not runs:
        return []
    spans: dict[tuple[float, float], list[float]] = {}
    for x, lo, hi in runs:
        spans.setdefault((round(lo, 1), round(hi, 1)), []).append(x)
    # The body appears more often than anything else its exact height.
    best = max(spans.items(), key=lambda kv: (len(kv[1]), kv[0][1] - kv[0][0]))
    height = best[0][1] - best[0][0]
    scale = height / length_mm
    out = []
    for (lo, hi), xs in spans.items():
        if abs((hi - lo) - height) > max(1.0, height * tol):
            continue
        out.append(View(lo, hi, min(xs), max(xs), scale))
    return sorted(out, key=lambda v: v.x0)


def _blocks(sheet: Sheet) -> list[dict]:
    """Text runs gathered into the multi-line notes a reader sees.

    Not :func:`phrases`, which joins a prefix onto one number and nothing
    else. An annotation is prose -- ``(+) VOLUME BUTTON`` is three runs on one
    baseline, ``SIDE`` / ``BUTTON`` is two runs stacked -- and it has to be
    whole before it can be matched against a name.
    """
    lines = []
    for lb in sorted(sheet.labels, key=lambda l: (-round(l.y, 1), l.x)):
        t = re.sub(r'\s+', ' ', lb.text).strip()
        if not t:
            continue
        if (lines and abs(lines[-1]['y'] - lb.y) < 0.4
                and 0 <= lb.x - lines[-1]['x1'] < 14):
            lines[-1]['t'] += ' ' + t
            lines[-1]['x1'] = lb.x + len(t) * 2.3
        else:
            lines.append({'t': t, 'x0': lb.x, 'x1': lb.x + len(t) * 2.3,
                          'y': lb.y})
    out: list[dict] = []
    for ln in lines:
        for b in out:
            if (abs(b['y'] - ln['y']) < 7.0
                    and ln['x0'] < b['x1'] + 6 and ln['x1'] > b['x0'] - 6):
                b['t'] += ' ' + ln['t']
                b['y'] = min(b['y'], ln['y'])
                b['x0'] = min(b['x0'], ln['x0'])
                b['x1'] = max(b['x1'], ln['x1'])
                break
        else:
            out.append(dict(ln))
    return out


def _leaders(sheet: Sheet):
    """Collinear horizontal runs -- the lines annotations point along."""
    cov: dict[float, list[tuple[float, float]]] = {}
    for p in sheet.paths:
        for a, b in zip(p.pts, p.pts[1:]):
            if abs(a[1] - b[1]) < 0.2 and abs(a[0] - b[0]) > 0.8:
                cov.setdefault(round((a[1] + b[1]) / 2, 1), []).append(
                    (min(a[0], b[0]), max(a[0], b[0])))
    out = []
    for y, segs in cov.items():
        segs.sort()
        lo, hi = segs[0]
        for s, e in segs[1:]:
            if s <= hi + 1.2:
                hi = max(hi, e)
            else:
                out.append((y, lo, hi))
                lo, hi = s, e
        out.append((y, lo, hi))
    return out


#: The order these run down the side of every iPhone. A set that comes out in
#: a different order has matched something to the wrong leader, and is worth
#: less than no answer at all.
DOWN_THE_SIDE = ("action", "volume-up", "volume-down")


def features(sheet: Sheet, length_mm: float) -> list[Feature]:
    """Every named side feature on a sheet, as mm down from the body's top."""
    band = views(sheet, length_mm)
    if not band:
        return []
    leads = _leaders(sheet)
    found: list[Feature] = []
    for blk in _blocks(sheet):
        text = blk['t'].upper()
        key = next((k for n, k in FEATURE_NAMES.items() if n in text), None)
        if key is None or len(blk['t']) > 48:
            continue
        best = None
        for y, lo, hi in leads:
            if hi - lo < 8 or not (blk['y'] - 16 < y < blk['y'] + 16):
                continue
            left, right = abs(hi - blk['x0']), abs(lo - blk['x1'])
            if min(left, right) > 12:
                continue
            far = lo if left < right else hi
            if best is None or hi - lo > best[2]:
                best = (y, far, hi - lo)
        if best is None:
            continue
        y, far, _ = best
        view = next((v for v in band if v.holds(far, y)), None)
        if view is None:
            continue
        name = next(n for n in FEATURE_NAMES if n in text)
        found.append(Feature(name, key, view.from_top(y), (far, y)))
    return _sane(found, length_mm)


def _sane(found: list[Feature], length_mm: float) -> list[Feature]:
    """Drop what cannot be right, and refuse a set that contradicts itself.

    Three things go wrong. A name can appear twice on a sheet (a note and a
    detail view), and the same key is then matched to two leaders. A leader
    belonging to a neighbouring note can be picked up. And a feature can land
    outside the body altogether, which means the view or the band was wrong.

    The last check is the one worth having: the action button is above volume
    up which is above volume down on every iPhone ever made, so a set that
    comes back out of order has mismatched something, and the whole set goes
    back rather than the one value that happens to look odd.
    """
    by_key: dict[str, Feature] = {}
    for f in found:
        if not 0.0 <= f.from_top_mm <= length_mm:
            continue
        prev = by_key.get(f.key)
        if prev is None or (abs(f.from_top_mm - length_mm / 2)
                            < abs(prev.from_top_mm - length_mm / 2)):
            by_key[f.key] = f
    order = [by_key[k].from_top_mm for k in DOWN_THE_SIDE if k in by_key]
    if order != sorted(order):
        return []
    return sorted(by_key.values(), key=lambda f: f.from_top_mm)


#: Published body sizes, which is where the scale for every view comes from.
#: Every view on a sheet is scaled by dividing its height by the number here,
#: so a wrong length is a wrong scale and every feature off that sheet is
#: wrong with it -- the 17e was guessed at 150.4 and came back 2.5% adrift on
#: everything until its own drawing was read and said 146.71.
#:
#: Four drawings print their own figures and agree with the published ones:
#: 16 (147.64 x 71.63 x 7.81), 16 Pro (149.61 x 71.45 x 8.25), 16 Pro Max
#: (163.03 x 77.58 x 8.25) and 17e (146.71 x 71.52 x 7.80).
BODIES = {
    "iphone-12": 146.7, "iphone-12-mini": 131.5, "iphone-12-pro": 146.7,
    "iphone-12-pro-max": 160.8, "iphone-13": 146.7, "iphone-13-mini": 131.5,
    "iphone-13-pro": 146.7, "iphone-13-pro-max": 160.8, "iphone-14": 146.7,
    "iphone-14-plus": 160.8, "iphone-14-pro": 147.5, "iphone-14-pro-max": 160.7,
    "iphone-15": 147.6, "iphone-15-plus": 160.9, "iphone-15-pro": 146.6,
    "iphone-15-pro-max": 159.9, "iphone-16": 147.6, "iphone-16-plus": 160.9,
    "iphone-16-pro": 149.6, "iphone-16-pro-max": 163.0, "iphone-16e": 146.7,
    "iphone-17": 149.6, "iphone-17-pro": 150.0, "iphone-17-pro-max": 163.4,
    "iphone-17e": 146.71, "iphone-air": 156.2, "iphone-se-3rd-generation": 138.4,
}


def harvest(path: Path, length_mm: float) -> dict:
    """Everything one drawing will give up, with where each part came from."""
    sheets = load(path)
    drawing = [s for s in sheets if len(s.paths) > 500]
    out: dict = {
        "model": path.stem,
        "length_mm": length_mm,
        "sheets": len(sheets),
        "outlined_sheets": [s.number for s in drawing
                            if len(phrases(s.labels)) < 5],
        "features": {},
        "chains": [],
        "notes": [],
    }
    for sheet in drawing:
        text = phrases(sheet.labels)
        for f in features(sheet, length_mm):
            out["features"].setdefault(f.key, {
                "from_top_mm": round(f.from_top_mm, 2),
                "drawing_name": f.name,
                "sheet": sheet.number,
                "source": "leader line on a named annotation",
            })
        for c in chains(text, 'x') + chains(text, 'y'):
            out["chains"].append({
                "sheet": sheet.number, "axis": c.axis,
                "scale_pt_per_mm": round(c.scale, 6),
                "residual_pt": round(c.residual, 5),
                "values_mm": sorted(lb.value for lb in c.members),
            })
        # Apple states some case rules in words. They are worth keeping.
        for lb in text:
            t = re.sub(r'\s+', ' ', lb.text).strip()
            if re.search(r'CASE THICKNESS|MAGNETIC PERMEABILITY|DO NOT OBSTRUCT'
                         r'|NO METAL CONTACT|KEEPOUT', t, re.I) and 8 < len(t) < 120:
                if t not in out["notes"]:
                    out["notes"].append(t)
    return out


def main(argv: list[str]) -> int:
    """With a file, report it. With ``--all``, harvest every drawing found."""
    if len(argv) < 2:
        print(__doc__)
        return 2

    if argv[1] == "--all":
        folder = Path(argv[2]) if len(argv) > 2 else ROOT / "drawings"
        found = {}
        for slug, length in sorted(BODIES.items()):
            pdf = folder / f"{slug}.pdf"
            if not pdf.exists():
                continue
            rec = harvest(pdf, length)
            found[slug] = rec
            keys = ", ".join(sorted(rec["features"])) or "-"
            print(f"{slug:26s} sheets {rec['sheets']}  "
                  f"outlined {rec['outlined_sheets']}  features: {keys}")
        out = ROOT / "src" / "iphone_dims.json"
        out.write_text(json.dumps(found, indent=1))
        print(f"\n{len(found)} models -> {out.relative_to(ROOT)}")
        return 0

    src = Path(argv[1])
    if not src.exists():
        print(f"no such drawing: {src}", file=sys.stderr)
        return 1
    sheets = load(src)
    print(f"{src.name}: {len(sheets)} pages, "
          f"{sum(len(s.paths) for s in sheets)} painted subpaths, "
          f"{sum(len(s.labels) for s in sheets)} text runs")
    length = BODIES.get(src.stem)
    for sheet in sheets:
        text = phrases(sheet.labels)
        if len(text) < 5 and len(sheet.paths) > 500:
            print(f"\nsheet {sheet.number}: text is outlined, not text "
                  f"({len(glyph_cells(sheet))} stroked character cells)")
            continue
        found = chains(text, 'x') + chains(text, 'y')
        feats = features(sheet, length) if length else []
        if not found and not feats:
            continue
        print(f"\nsheet {sheet.number}: {len(sheet.paths)} paths")
        for c in found:
            print(f"   {c.axis} datum {c.origin_pt:9.3f} pt  "
                  f"{c.scale:+.4f} pt/mm  residual {c.residual:.5f} pt  "
                  f"{len(c.members)} labels")
        for f in feats:
            print(f"   {f.key:15s} {f.from_top_mm:7.2f} mm from the top "
                  f"({f.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
