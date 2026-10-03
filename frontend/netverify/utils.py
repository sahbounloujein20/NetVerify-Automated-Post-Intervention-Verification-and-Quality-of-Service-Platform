"""Data formatting and normalisation for display.

The numeric and date conventions are deliberately kept as they are (comma as
the decimal separator, narrow no-break space as the thousands separator,
dd/mm/yyyy dates); only the words are in English.
"""

from __future__ import annotations

import html
import math
from datetime import datetime
from typing import Any

import pandas as pd

from .settings import MONTH_LABELS

NBSP = " "  # narrow no-break space — thousands separator


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return default if math.isnan(result) or math.isinf(result) else result
    except (TypeError, ValueError):
        return default


def fmt_int(value: Any) -> str:
    """1284 -> "1 284" """
    return f"{int(round(to_float(value))):,}".replace(",", NBSP)


def fmt_compact(value: Any) -> str:
    """Abbreviates large numbers: 12 940 -> "12,9 K" """
    number = to_float(value)
    for limit, suffix in ((1e9, "Bn"), (1e6, "M"), (1e3, "K")):
        if abs(number) >= limit:
            return f"{number / limit:.1f}".replace(".", ",").rstrip("0").rstrip(",") + f"{NBSP}{suffix}"
    return fmt_int(number)


def fmt_pct(value: Any, digits: int = 1) -> str:
    return f"{to_float(value):.{digits}f}".replace(".", ",") + "%"


def fmt_mbps(kbps: Any) -> str:
    """Rate in kb/s -> "20,5 Mb/s" """
    return f"{to_float(kbps) / 1024:.1f}".replace(".", ",") + " Mb/s"


def ratio(part: Any, whole: Any, digits: int = 1) -> float:
    """Safe percentage (0 when the denominator is zero)."""
    total = to_float(whole)
    return round(to_float(part) / total * 100, digits) if total else 0.0


def variation(current: Any, previous: Any) -> float | None:
    """Relative change in % between two periods, `None` if not computable."""
    before = to_float(previous)
    if not before:
        return None
    return round((to_float(current) - before) / before * 100, 1)


def fmt_signed_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{'+' if value > 0 else ''}{value:.1f}".replace(".", ",") + "%"


def fmt_month(code: Any) -> str:
    """"2026-07" -> "Jul 2026" """
    text = str(code or "")
    if len(text) == 7 and text[4] == "-":
        year, month = text[:4], text[5:7]
        return f"{MONTH_LABELS.get(month, month)} {year}"
    return text


def fmt_datetime(value: Any, with_time: bool = True) -> str:
    """Normalises the ISO dates returned by the API."""
    if not value:
        return "—"
    text = str(value).replace("Z", "").split(".")[0]
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            moment = datetime.strptime(text, pattern)
            return moment.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")
        except ValueError:
            continue
    return text


def esc(value: Any) -> str:
    """Escapes a value destined for an HTML block."""
    return html.escape(str(value if value is not None else "—"), quote=True)


def to_frame(records: Any, numeric: tuple[str, ...] = ()) -> pd.DataFrame:
    """Builds a DataFrame that is robust to any API response."""
    frame = pd.DataFrame(records if isinstance(records, list) else [])
    for column in numeric:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame


def technologie_de(reference: Any) -> str:
    """Extracts the technology from the prefix of a reference ("GPON/2026/15002")."""
    return str(reference or "").split("/")[0].upper() or "—"


def search_frame(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    """Full-text filter, case-insensitive, across every column."""
    if not query.strip() or frame.empty:
        return frame
    mask = frame.astype(str).apply(
        lambda column: column.str.contains(query.strip(), case=False, na=False, regex=False)
    )
    return frame[mask.any(axis=1)]
