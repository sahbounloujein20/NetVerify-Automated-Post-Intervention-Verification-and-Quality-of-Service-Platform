"""
Icon set.

Rendered as Material Symbols ligatures, not as inline SVG: `st.html` sanitises
its content with DOMPurify in HTML-only profile (`USE_PROFILES: {html: true}`),
which silently strips every `<svg>` tag. A `<span>` carrying the icon font goes
through the filter.

The font is already bundled by Streamlit (`MaterialSymbols-Rounded.woff2`), so
nothing is fetched from the internet and the rendering stays identical offline.

Only standard glyph names are used. As a last resort, the CSS rule `.nv-icon`
encloses the glyph in a 1 em box with `overflow: hidden`: were a ligature to be
missing, the name would be truncated instead of spilling over the neighbouring
text.
"""

from __future__ import annotations

# business name -> Material Symbols glyph
_GLYPHS: dict[str, str] = {
    "grid": "space_dashboard",
    "users": "groups",
    "inbox": "inbox",
    "chart": "insights",
    "map-pin": "location_on",
    "list": "receipt_long",
    "refresh": "refresh",
    "activity": "monitoring",
    "check": "check_circle",
    "alert": "warning",
    "clock": "schedule",
    "gauge": "speed",
    "signal": "network_check",
    "database": "storage",
    "search": "search",
    "download": "download",
    "shield": "verified_user",
    "zap": "bolt",
    "server": "dns",
    "trend-up": "trending_up",
    "trend-down": "trending_down",
    "target": "flag",
    "layers": "layers",
    "file": "description",
    "wifi": "wifi",
    "sliders": "tune",
    "arrow-up": "arrow_upward",
    "arrow-down": "arrow_downward",
}

FALLBACK = "info"


def icon(name: str, size: int = 16, color: str = "currentColor", stroke: float = 1.8) -> str:
    """Markup of an icon, ready to be inserted into an HTML block.

    `stroke` is kept for compatibility with the existing calls; it has had no
    effect since the move to glyphs.
    """
    glyph = _GLYPHS.get(name, FALLBACK)
    return (
        f'<span class="nv-icon" style="font-size:{size}px;color:{color}" '
        f'aria-hidden="true">{glyph}</span>'
    )
