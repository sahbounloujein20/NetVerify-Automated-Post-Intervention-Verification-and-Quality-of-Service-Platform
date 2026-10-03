"""
The Tunisie Telecom mark, inlined into the pages.

The asset is embedded as a `data:` URI rather than served from a URL: the
headers are built with `st.html`, which has no access to the Streamlit static
folder unless it is explicitly enabled, and an image that failed to load would
leave the navigation bar without its logo.

Two variants live in `assets/`:

    tt-logo   full lockup, with "Tunisie Telecom" inside the drop
    tt-mark   the drop and its TT alone, legible down to 32 px

The corporate artwork takes precedence over the vector rendering produced by
`assets/make_brand.py`: save it as `assets/tt-logo.png` (or `tt-mark.png`) and
it is picked up on the next start, nothing else to change.

The module sits next to `theme.py` and not in `ui/`: `auth.py` needs the mark
for the sign-in screen, and going through the component package would drag
the whole chart library in before the session is even open.
"""

from __future__ import annotations

from base64 import b64encode
from functools import lru_cache
from pathlib import Path

from .settings import ORG_NAME
from .utils import esc

ASSETS = Path(__file__).resolve().parents[1] / "assets"

# Order of preference: the corporate raster first, the generated vector after.
SOURCES = ((".png", "image/png"), (".svg", "image/svg+xml"))

LOCKUP = "tt-logo"
MARK = "tt-mark"


@lru_cache(maxsize=None)
def data_uri(stem: str) -> str:
    """`data:` URI of the asset, or an empty string when none is present."""
    for suffix, mime in SOURCES:
        path = ASSETS / f"{stem}{suffix}"
        if path.exists():
            return f"data:{mime};base64,{b64encode(path.read_bytes()).decode('ascii')}"
    return ""


def logo(css_class: str, stem: str = MARK) -> str:
    """`<img>` of the mark, or a text badge when the asset is missing.

    The fallback is not decorative: a checkout where `make_brand.py` has never
    been run must still show a readable header rather than a broken image.
    """
    uri = data_uri(stem)
    if not uri:
        return f'<div class="{esc(css_class)} logo-fallback">TT</div>'
    return f'<img class="{esc(css_class)}" src="{uri}" alt="{esc(ORG_NAME)}">'


__all__ = ["LOCKUP", "MARK", "data_uri", "logo"]
