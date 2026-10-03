"""
Generates the Tunisie Telecom brand assets carried by the dashboard.

    python assets/make_brand.py

Three files land next to this script:

    tt-logo.svg   full lockup — drop + TT + "Tunisie Telecom" (sign-in, hero)
    tt-mark.svg   drop + TT only (navigation badge, small sizes)
    favicon.png   256 px raster of the mark (browser tab)

The drop is rebuilt from its geometry rather than traced by hand, so the
project carries no asset that depends on a font or an image editor being
installed. The corporate artwork stays authoritative: drop it next to this
script as `tt-logo.png` / `tt-mark.png` and `netverify/ui/brand.py` will
prefer it over the generated SVG, without a single line to change elsewhere.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent

# ── Geometry of the drop ──────────────────────────────────────────────────────
# Round bulb on the left, tip on the right, on the horizontal mid-line. The
# ratio bulb/tip is what fixes the silhouette: 1.51 wide for 1 high, as on the
# corporate logo.
VIEW_W, VIEW_H = 115.0, 76.0
CENTRE = (38.0, 38.0)
RADIUS = 38.0
TIP = (114.6, 38.0)

# Where every facet converges — slightly to the right of the bulb centre.
FOCUS = (40.0, 38.0)

# ── Colours ───────────────────────────────────────────────────────────────────
# The wheel is read clockwise from the top (270° = up, 0° = the tip). Anchors
# are the corporate hues; everything in between is interpolated in RGB, then
# shaded per facet to obtain the low-poly relief.
PALETTE: list[tuple[float, str]] = [
    (270, "#00A88E"),   # up          — green-teal
    (300, "#39B54A"),   # upper right — green
    (330, "#8DC63F"),   #             — yellow-green
    (360, "#FFDE17"),   # tip         — yellow
    (390, "#F7941E"),   # lower right — orange
    (420, "#F15A29"),   #             — orange-red
    (450, "#ED1C24"),   # down        — red
    (480, "#EC008C"),   # lower left  — pink
    (510, "#A0248F"),   #             — magenta
    (540, "#662D91"),   # left        — purple
    (570, "#2E3192"),   # upper left  — indigo
    (600, "#0071BC"),   #             — blue
    (615, "#00AEEF"),   #             — cyan
    (630, "#00A88E"),   # up again
]

SECTORS = 22          # radial cuts around the focus
BANDS = 3             # facets per sector, from the focus to the outline
SEED = 7              # fixed: the generated files must not move between runs

# The rim facets are cut on the chord joining two rays, which falls short of
# the curve — and misses the tip entirely. They are pushed past the outline
# and the clip trims them back to it.
OVERSHOOT = 1.4

# ── The TT monogram ───────────────────────────────────────────────────────────
TT_TOP, TT_BOTTOM = 18.1, 52.2
TT_BAR = 9.2          # thickness of the horizontal bar
TT_WIDTH = 27.0       # width of one T
TT_STEM = 11.5        # width of the vertical stem
TT_LEFT = 10.5        # left edge of the first T
TT_GAP = 6.5          # space between the two T

WORDMARK = "Tunisie Telecom"
WORD_LEFT, WORD_RIGHT = 11.9, 69.5
WORD_BASELINE = 60.6
WORD_SIZE = 8.6


# ══════════════════════════════════════════════════════════════════════════════
# Outline
# ══════════════════════════════════════════════════════════════════════════════

def _tangents() -> tuple[float, float, tuple[float, float], tuple[float, float]]:
    """Bulb axis, half-angle, and the two points where the tip meets it."""
    span = math.hypot(TIP[0] - CENTRE[0], TIP[1] - CENTRE[1])
    axis = math.atan2(TIP[1] - CENTRE[1], TIP[0] - CENTRE[0])
    half = math.acos(RADIUS / span)
    top = (CENTRE[0] + RADIUS * math.cos(axis - half),
           CENTRE[1] + RADIUS * math.sin(axis - half))
    bottom = (CENTRE[0] + RADIUS * math.cos(axis + half),
              CENTRE[1] + RADIUS * math.sin(axis + half))
    return axis, half, top, bottom


def drop_path() -> str:
    """The outline as an SVG path: the long arc of the bulb, then the tip."""
    _, _, top, bottom = _tangents()
    return (f"M {top[0]:.3f} {top[1]:.3f} "
            f"A {RADIUS} {RADIUS} 0 1 0 {bottom[0]:.3f} {bottom[1]:.3f} "
            f"L {TIP[0]:.3f} {TIP[1]:.3f} Z")


def drop_polygon(steps: int = 240) -> list[tuple[float, float]]:
    """The same outline sampled — used for the raster and for the ray casts."""
    axis, half, _, _ = _tangents()
    start = axis - half
    sweep = 2 * math.pi - 2 * half          # the long way round, away from the tip
    points = [
        (CENTRE[0] + RADIUS * math.cos(start - sweep * i / steps),
         CENTRE[1] + RADIUS * math.sin(start - sweep * i / steps))
        for i in range(steps + 1)
    ]
    points.append(TIP)
    return points


def _reach(angle_deg: float, outline: list[tuple[float, float]]) -> float:
    """Distance from the focus to the outline, along `angle_deg`.

    The facets are cut as a fraction of that distance and not of a fixed
    radius: the tip is twice as far as the left flank, and a fixed radius
    would leave the tip with a single flat facet.
    """
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle), math.sin(angle)
    best = 0.0
    for (x1, y1), (x2, y2) in zip(outline, outline[1:] + outline[:1]):
        ex, ey = x2 - x1, y2 - y1
        denominator = dx * ey - dy * ex
        if abs(denominator) < 1e-12:
            continue
        fx, fy = x1 - FOCUS[0], y1 - FOCUS[1]
        t = (fx * ey - fy * ex) / denominator      # along the ray
        u = (fx * dy - fy * dx) / denominator      # along the segment
        if t > 0 and -1e-9 <= u <= 1 + 1e-9:
            best = max(best, t)
    return best


# ══════════════════════════════════════════════════════════════════════════════
# Colours
# ══════════════════════════════════════════════════════════════════════════════

def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def wheel(angle_deg: float) -> tuple[int, int, int]:
    """Corporate colour at that angle, interpolated between two anchors."""
    angle = 270 + (angle_deg - 270) % 360
    for (a1, c1), (a2, c2) in zip(PALETTE, PALETTE[1:]):
        if a1 <= angle <= a2:
            t = (angle - a1) / (a2 - a1)
            start, end = _rgb(c1), _rgb(c2)
            return tuple(round(start[k] + (end[k] - start[k]) * t) for k in range(3))
    return _rgb(PALETTE[-1][1])


def shade(colour: tuple[int, int, int], factor: float) -> str:
    """Lightens or darkens a facet — this is what makes the relief read."""
    return "#%02X%02X%02X" % tuple(min(255, max(0, round(c * factor))) for c in colour)


# ══════════════════════════════════════════════════════════════════════════════
# Faceting
# ══════════════════════════════════════════════════════════════════════════════

def facets() -> list[tuple[list[tuple[float, float]], str]]:
    """The polygons of the mosaic, each with its colour.

    Every ray carries its own cut fractions, so two neighbouring sectors never
    break at the same distance: the mosaic tiles the drop without a gap while
    keeping the irregular look of the logo.
    """
    random.seed(SEED)
    outline = drop_polygon()

    rays = []
    for i in range(SECTORS):
        angle = 270 + i * 360 / SECTORS + random.uniform(-4.0, 4.0)
        cuts = [0.0, random.uniform(0.26, 0.40), random.uniform(0.58, 0.76), OVERSHOOT]
        rays.append((angle, _reach(angle, outline), cuts))

    tiles = []
    for i, (angle_a, reach_a, cuts_a) in enumerate(rays):
        angle_b, reach_b, cuts_b = rays[(i + 1) % SECTORS]
        if angle_b < angle_a:
            angle_b += 360
        middle = (angle_a + angle_b) / 2
        base = wheel(middle + random.uniform(-4.0, 4.0))

        for band in range(BANDS):
            inner_a, outer_a = cuts_a[band] * reach_a, cuts_a[band + 1] * reach_a
            inner_b, outer_b = cuts_b[band] * reach_b, cuts_b[band + 1] * reach_b
            corners = [
                _point(angle_a, inner_a), _point(angle_a, outer_a),
                _point(angle_b, outer_b), _point(angle_b, inner_b),
            ]
            # The inner ring reads slightly lighter, the rim slightly deeper:
            # the drop keeps a centre of gravity instead of looking flat.
            factor = (1.10, 0.98, 1.04)[band] * random.uniform(0.94, 1.06)
            tiles.append((corners, shade(base, factor)))
    return tiles


def _point(angle_deg: float, distance: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    return (FOCUS[0] + distance * math.cos(angle), FOCUS[1] + distance * math.sin(angle))


# ══════════════════════════════════════════════════════════════════════════════
# The monogram
# ══════════════════════════════════════════════════════════════════════════════

def tee(left: float) -> list[tuple[float, float]]:
    """One T, drawn as an outline: no font needed at any size."""
    right = left + TT_WIDTH
    bar = TT_TOP + TT_BAR
    stem_left = left + (TT_WIDTH - TT_STEM) / 2
    stem_right = stem_left + TT_STEM
    return [
        (left, TT_TOP), (right, TT_TOP), (right, bar),
        (stem_right, bar), (stem_right, TT_BOTTOM),
        (stem_left, TT_BOTTOM), (stem_left, bar), (left, bar),
    ]


def monogram() -> list[list[tuple[float, float]]]:
    return [tee(TT_LEFT), tee(TT_LEFT + TT_WIDTH + TT_GAP)]


# ══════════════════════════════════════════════════════════════════════════════
# SVG
# ══════════════════════════════════════════════════════════════════════════════

def _points(polygon) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in polygon)


def build_svg(with_wordmark: bool, clip_id: str) -> str:
    tiles = "\n".join(
        f'    <polygon points="{_points(corners)}" fill="{colour}" '
        f'stroke="{colour}" stroke-width="0.3"/>'
        for corners, colour in facets()
    )
    letters = "\n".join(f'    <polygon points="{_points(t)}"/>' for t in monogram())

    word = ""
    if with_wordmark:
        # `textLength` pins the width whatever font the machine resolves, so
        # the wordmark never overflows the drop.
        word = (
            f'\n  <text x="{WORD_LEFT:.2f}" y="{WORD_BASELINE:.2f}" fill="#ffffff"\n'
            f'        font-family="Segoe UI, Helvetica Neue, Arial, sans-serif"\n'
            f'        font-size="{WORD_SIZE}" font-weight="500"\n'
            f'        textLength="{WORD_RIGHT - WORD_LEFT:.2f}" '
            f'lengthAdjust="spacingAndGlyphs">{WORDMARK}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W:g} {VIEW_H:g}" \
role="img" aria-label="Tunisie Telecom">
  <title>Tunisie Telecom</title>
  <defs>
    <clipPath id="{clip_id}"><path d="{drop_path()}"/></clipPath>
  </defs>
  <g clip-path="url(#{clip_id})">
{tiles}
  </g>
  <g fill="#ffffff">
{letters}
  </g>{word}
</svg>
"""


# ══════════════════════════════════════════════════════════════════════════════
# Favicon
# ══════════════════════════════════════════════════════════════════════════════

FAVICON_SIZE = 256
FAVICON_PAD = 8
SUPERSAMPLE = 4


def build_favicon() -> Path:
    """The mark alone, fitted to the width of a square canvas."""
    size = FAVICON_SIZE * SUPERSAMPLE
    pad = FAVICON_PAD * SUPERSAMPLE
    scale = (size - 2 * pad) / VIEW_W
    offset_y = (size - VIEW_H * scale) / 2

    def to_px(polygon):
        return [(pad + x * scale, offset_y + y * scale) for x, y in polygon]

    mosaic = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    painter = ImageDraw.Draw(mosaic)
    for corners, colour in facets():
        painter.polygon(to_px(corners), fill=colour, outline=colour, width=SUPERSAMPLE)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(to_px(drop_polygon()), fill=255)

    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon.paste(mosaic, (0, 0), mask)

    painter = ImageDraw.Draw(icon)
    for letter in monogram():
        painter.polygon(to_px(letter), fill=(255, 255, 255, 255))

    output = HERE / "favicon.png"
    icon.resize((FAVICON_SIZE, FAVICON_SIZE), Image.LANCZOS).save(output, "PNG")
    return output


# ══════════════════════════════════════════════════════════════════════════════

def build() -> list[Path]:
    written = []
    for name, wordmark, clip_id in (
        ("tt-logo.svg", True, "tt-logo-drop"),
        ("tt-mark.svg", False, "tt-mark-drop"),
    ):
        path = HERE / name
        path.write_text(build_svg(wordmark, clip_id), encoding="utf-8")
        written.append(path)
    written.append(build_favicon())
    return written


if __name__ == "__main__":
    for created in build():
        print(f"{created.name} — {created.stat().st_size} bytes")
