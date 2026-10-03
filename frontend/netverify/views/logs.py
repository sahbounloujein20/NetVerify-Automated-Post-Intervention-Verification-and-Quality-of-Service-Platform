"""Control journal — anomalies detected by the D+14 comparator."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from .. import api
from ..utils import fmt_datetime, fmt_int, fmt_pct, ratio, search_frame, to_frame
from ..ui import cards, charts, shell, states, tables
from ..ui.cards import FeedItem, Tile

# "ANOMALIE" and "OK" are the values stored in `statut_test`; only the labels
# shown in the selector are translated (see `format_func` below).
STATUTS = ["All", "ANOMALIE", "OK"]


def render() -> None:
    shell.render_page_header(
        "Control journal",
        "Traceability of the automatic verifications: every gap detected is "
        "timestamped, attached to a work order and diagnosed.",
        "list",
    )

    status_value, limit, search = _filters()
    result = api.get("/logs", statut_test=status_value, limit=limit)

    if result.failed:
        states.offline_banner()
        with shell.card("logs-error"):
            states.error_state(result, "the control journal")
        return
    if result.empty:
        _kpi_row(pd.DataFrame())
        shell.spacer(10)
        with shell.card("logs-vide"):
            states.empty_state(
                "Empty journal",
                "No verification has produced an entry for this filter yet. "
                "Run a D+14 control from the Work orders page.",
                "shield",
            )
        return

    frame = to_frame(result.list())
    filtered = search_frame(frame, search).reset_index(drop=True)

    _kpi_row(filtered)
    shell.spacer(10)

    left, right = st.columns([1.35, 1], gap="medium")
    with left:
        _tendance_card(filtered)
    with right:
        _recentes_card(filtered)

    shell.spacer(10)
    _table_card(filtered, len(frame), search)


# ══════════════════════════════════════════════════════════════════════════════

def _filters() -> tuple[str, int, str]:
    with shell.card("logs-filtres"):
        col1, col2, col3 = st.columns([1, 1, 2], vertical_alignment="bottom")
        with col1:
            status_value = st.selectbox(
                "Status", STATUTS, key="log_statut",
                format_func=lambda s: {"ANOMALIE": "Anomaly", "OK": "Compliant"}.get(s, s),
            )
        with col2:
            limit = st.number_input("Entries loaded", 25, 500, 200, step=25, key="log_limit")
        with col3:
            search = st.text_input(
                "Search", placeholder="Reference, diagnosis, cause…", key="log_search"
            )
    return status_value, int(limit), search


def _kpi_row(frame: pd.DataFrame) -> None:
    total = len(frame)
    anomalies = int((frame["statut_test"] == "ANOMALIE").sum()) if "statut_test" in frame else 0
    compliant_rows = total - anomalies

    today_count = 0
    if "date_test" in frame and total:
        day = datetime.now().strftime("%Y-%m-%d")
        today_count = int(frame["date_test"].astype(str).str.startswith(day).sum())

    cards.tile_row([
        Tile(label="Entries analysed", value=fmt_int(total), icon="file", note="On the current filter"),
        Tile(label="Anomalies", value=fmt_int(anomalies), icon="alert",
             tone="critical" if anomalies else "good",
             note=f"{fmt_pct(ratio(anomalies, total))} of the entries" if total else "No gap"),
        Tile(label="Compliant controls", value=fmt_int(compliant_rows), icon="shield", tone="good",
             note="Rate matching the profile"),
        Tile(label="Detected today", value=fmt_int(today_count), icon="clock",
             tone="warning" if today_count else "good", note=datetime.now().strftime("%d/%m/%Y")),
    ])


def _tendance_card(frame: pd.DataFrame) -> None:
    with shell.card("logs-tendance", height="stretch"):
        shell.section(
            "Control volume per day",
            "Detection pace over the loaded period.",
        )
        if "date_test" not in frame or frame.empty:
            states.empty_state("No history", "The entries carry no usable date.", "clock")
            return

        series_values = pd.to_datetime(
            frame["date_test"], errors="coerce", format="mixed"
        ).dt.normalize().dropna()
        if series_values.empty:
            states.empty_state("No history", "No usable date in the journal.", "clock")
            return

        # A day without a control is a zero, not a missing category: counting the
        # values alone would place two days a week apart side by side and the
        # pace read off the curve would be false.
        daily = series_values.value_counts().reindex(
            pd.date_range(series_values.min(), series_values.max(), freq="D"),
            fill_value=0,
        )

        labels = [day.strftime("%d/%m") for day in daily.index]
        # A pace needs at least two days to exist. When the journal holds a
        # single one, the curve has nothing to join and would leave the frame
        # empty: the volume of that day is shown as a column, value on top.
        figure = (
            charts.columns(labels, daily.values, min_slots=7)
            if len(labels) == 1
            else charts.area(labels, daily.values, "Controls")
        )
        charts.show(figure, height=282, key="log_tendance")
        charts.table_twin(
            pd.DataFrame({"Day": labels, "Controls": daily.values})
        )


def _recentes_card(frame: pd.DataFrame) -> None:
    with shell.card("logs-recentes", height="stretch"):
        shell.section("Most recent alerts", "The last five entries of the journal.")
        if frame.empty:
            states.empty_state("No alert", "Nothing to report on the current filter.", "shield")
            return

        cards.feed([
            FeedItem(
                title=entry.get("ref_demande") or "—",
                message=entry.get("message_log") or "—",
                timestamp=fmt_datetime(entry.get("date_test")),
                tone="critical" if entry.get("statut_test") == "ANOMALIE" else "good",
                tag="Anomaly" if entry.get("statut_test") == "ANOMALIE" else "Compliant",
            )
            for entry in frame.head(5).to_dict("records")
        ])


def _table_card(frame: pd.DataFrame, total_charge: int, search: str) -> None:
    with shell.card("logs-table"):
        shell.section(
            "Full journal",
            "Complete diagnosis produced by the comparator for every gap.",
            aside=f"{fmt_int(len(frame))} / {fmt_int(total_charge)} entries",
        )
        if frame.empty:
            states.empty_state("No result", f"No entry matches \"{search}\".", "search")
            return

        columns = [c for c in ("id_log", "ref_demande", "statut_test", "message_log", "date_test")
                    if c in frame.columns]
        tables.data_table(
            frame,
            key="logs_table",
            height=420,
            columns=columns,
            config={
                "id_log": tables.number_col("id_log"),
                "ref_demande": tables.text_col("ref_demande", "medium"),
                "statut_test": tables.text_col("statut_test", "small"),
                "message_log": tables.text_col("message_log", "large"),
                "date_test": tables.datetime_col("date_test"),
            },
        )
        tables.export_button(frame, "netverify_journal.csv", "logs_export")
