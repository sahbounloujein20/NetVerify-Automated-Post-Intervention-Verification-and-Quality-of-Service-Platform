"""Key-figure tiles, gauges, badges and alert feed.

The anatomy reuses that of the original cards — icon chip, title, big figure,
label — with three additions: the change against the previous period, the
micro trend curve and the objective gauge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import streamlit as st

from .. import theme
from ..utils import esc, fmt_signed_pct, to_float
from .icons import icon


# ══════════════════════════════════════════════════════════════════════════════
# Sparkline
# ══════════════════════════════════════════════════════════════════════════════

def sparkline(values: Sequence[float], color: str | None = None, height: int = 34) -> str:
    """Micro trend histogram, made of CSS bars.

    Deliberately not SVG: `st.html` goes through DOMPurify in HTML-only profile,
    which strips `<svg>` tags. Variable-height `<i>` elements pass the filter
    and give the same at-a-glance reading.
    """
    points = [to_float(v) for v in values if v is not None]
    if len(points) < 2:
        return ""

    color = color or theme.BRAND
    low, high = min(points), max(points)
    span = (high - low) or 1.0

    barres = []
    for index, value in enumerate(points):
        # 14% floor: a minimum value stays visible instead of disappearing
        # completely into the baseline.
        height = 14 + ((value - low) / span) * 86
        latest = index == len(points) - 1
        barres.append(
            f'<i style="height:{height:.1f}%;background:{color};'
            f'opacity:{"1" if latest else ".42"}"></i>'
        )
    return f'<div class="spark" style="height:{height}px">{"".join(barres)}</div>'


# ══════════════════════════════════════════════════════════════════════════════
# KPI tiles
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Tile:
    """One key figure.

    label     heading of the card
    value     already formatted value
    unit      discreet suffix ("%", "Mb/s")
    icon      icon name from the in-house set
    delta     relative change in % (None = no comparison available)
    delta_up_is_good  business meaning of the change
    note      context of the change, or an addition
    trend     series for the micro curve (optional)
    meter     (value, target) to show a gauge instead of a curve
    tone      accent of the card: brand | good | warning | critical | neutral
    """

    label: str
    value: str
    unit: str = ""
    icon: str = "activity"
    delta: float | None = None
    delta_up_is_good: bool = True
    note: str = ""
    trend: Sequence[float] = field(default_factory=tuple)
    meter: tuple[float, float] | None = None
    tone: str = "brand"


# tone -> (chip class, accent colour)
_TONES = {
    "brand": ("icon-primary", theme.BRAND_300),
    "good": ("icon-green", theme.STATUS["good"]),
    "warning": ("icon-amber", theme.STATUS["warning"]),
    "critical": ("icon-red", theme.STATUS_TEXT["critical"]),
    "neutral": ("icon-neutral", theme.INK_3),
}


def _delta_html(tile: Tile) -> str:
    if tile.delta is None:
        return esc(tile.note) if tile.note else ""

    improving = (tile.delta >= 0) == tile.delta_up_is_good
    color = theme.STATUS_TEXT["good"] if improving else theme.STATUS_TEXT["critical"]
    arrow = "arrow-up" if tile.delta >= 0 else "arrow-down"
    note = f"<span>{esc(tile.note)}</span>" if tile.note else ""
    return (
        f'<span class="kpi-delta" style="color:{color}">{icon(arrow, 13, color, 2.2)}'
        f"{fmt_signed_pct(tile.delta)}</span>{note}"
    )


def _meter_html(current: float, target: float, color: str) -> str:
    pct = max(0.0, min(100.0, (current / target * 100) if target else 0.0))
    return f"""
    <div class="meter">
      <div class="meter-track"><div class="meter-fill"
           style="width:{pct:.1f}%;background:{color}"></div></div>
      <div class="meter-scale"><span>0</span><span>Target {target:g}</span></div>
    </div>
    """


def _tile_html(tile: Tile) -> str:
    chip_class, accent = _TONES.get(tile.tone, _TONES["brand"])
    unit = f'<span class="kpi-unit">{esc(tile.unit)}</span>' if tile.unit else ""

    if tile.meter is not None:
        bottom = _meter_html(tile.meter[0], tile.meter[1], accent)
    else:
        bottom = sparkline(tile.trend, accent)

    return f"""
    <div class="card">
      <div class="card-title">
        <div class="card-icon {chip_class}">{icon(tile.icon, 20, accent)}</div>
        {esc(tile.label)}
      </div>
      <div class="kpi-row">
        <div>
          <div class="kpi-value">{esc(tile.value)}{unit}</div>
          <div class="kpi-label">{_delta_html(tile)}</div>
        </div>
      </div>
      {bottom}
    </div>
    """


def tile_row(tiles: Sequence[Tile]) -> None:
    """Row of cards in a fluid grid (equal heights, without Streamlit columns)."""
    if not tiles:
        return
    st.html(f'<div class="kpi-grid">{"".join(_tile_html(t) for t in tiles)}</div>')


# ══════════════════════════════════════════════════════════════════════════════
# Badges & alert feed
# ══════════════════════════════════════════════════════════════════════════════

def badge(label: str, tone: str = "neutral", dot: bool = True) -> str:
    """Markup of a badge — to be composed inside an HTML block."""
    colours = {"good": "var(--green)", "warning": "var(--amber)", "critical": "var(--red)"}
    marker = f'<span class="dot" style="background:{colours[tone]}"></span>' if dot and tone in colours else ""
    return f'<span class="badge {tone}">{marker}{esc(label)}</span>'


@dataclass
class FeedItem:
    title: str
    message: str
    timestamp: str = ""
    tone: str = "critical"
    tag: str = ""


def feed(items: Sequence[FeedItem]) -> None:
    """Event feed (alerts, journal) — the coloured-edge boxes of v1."""
    rows = []
    for item in items:
        colour = theme.STATUS.get(item.tone, theme.STATUS["critical"])
        text_colour = theme.STATUS_TEXT.get(item.tone, theme.STATUS_TEXT["critical"])
        tag = (
            f'<span style="color:{text_colour};font-size:12px;font-weight:750">{esc(item.tag)}</span>'
            if item.tag else ""
        )
        rows.append(
            f"""
            <div class="feed-item" style="border-left-color:{colour}">
              <div class="feed-head"><span class="feed-ref">{esc(item.title)}</span>{tag}</div>
              <div class="feed-msg">{esc(item.message)}</div>
              <div class="feed-time">{esc(item.timestamp)}</div>
            </div>
            """
        )
    st.html(f'<div class="feed">{"".join(rows)}</div>')
