"""Audit trail — who triggered the privileged operations, and who was refused.

The control journal (`Logs`) says what the D+14 verification *found*. This page
says who *asked* for it. The two are deliberately separate: one is a business
result, the other is an access trace, and mixing them would bury the second in
the volume of the first.

Restricting an action is only half a control. Without this page, nothing would
let a supervisor establish afterwards which account launched an estate-wide run
at 14:03, whether it succeeded, or that a technician account tried and was
turned away. The refusals are shown alongside the successes, because an attempt
that authorisation stopped is the most informative line of the journal.

The only page with neither key-figure tiles nor a chart: it is read one event at
a time, and "3 refused attempts" answers nothing without the three lines behind
it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import api
from ..settings import (
    AUDIT_ACTION_LABELS,
    AUDIT_OUTCOME_LABELS,
    AUDIT_OUTCOME_TONES,
    AUDIT_OUTCOMES,
)
from ..utils import fmt_datetime, fmt_int, search_frame, to_frame
from ..ui import cards, shell, states, tables
from ..ui.cards import FeedItem


def render() -> None:
    shell.render_page_header(
        "Audit trail",
        "Traceability of the privileged operations: the bulk runs, their "
        "outcome, and the attempts that authorisation refused.",
        "shield",
    )

    outcome, limit, search = _filters()
    result = api.get("/audit", resultat=outcome, limit=limit)

    if result.failed:
        states.offline_banner()
        with shell.card("audit-error"):
            states.error_state(result, "the audit trail")
        return

    if result.empty:
        with shell.card("audit-empty"):
            states.empty_state(
                "Empty journal",
                "No privileged action has been recorded for this filter yet. "
                "The journal fills up as soon as a D+14 control or a global "
                "refresh is triggered.",
                "shield",
            )
        return

    frame = to_frame(result.list())
    filtered = search_frame(frame, search).reset_index(drop=True)

    # No key-figure tiles and no chart here, unlike the other pages. An audit
    # trail is read one event at a time — "who did what, when, and did it work" —
    # and a count of refusals says nothing without the line behind it. Whoever
    # opens this page is looking for a specific action, not a trend.
    _recent_card(filtered)
    shell.spacer(10)
    _table_card(filtered, len(frame), search)


# ══════════════════════════════════════════════════════════════════════════════

def _label_outcome(value: str) -> str:
    return AUDIT_OUTCOME_LABELS.get(value, value)


def _label_action(value: str) -> str:
    """Endpoint path -> business wording, path kept when unknown."""
    return AUDIT_ACTION_LABELS.get(value, value)


def _filters() -> tuple[str, int, str]:
    with shell.card("audit-filters"):
        col1, col2, col3 = st.columns([1, 1, 2], vertical_alignment="bottom")
        with col1:
            outcome = st.selectbox(
                "Outcome", AUDIT_OUTCOMES, key="audit_outcome",
                format_func=lambda v: _label_outcome(v) if v != "All" else v,
            )
        with col2:
            limit = st.number_input(
                "Entries loaded", 25, 500, 150, step=25, key="audit_limit"
            )
        with col3:
            search = st.text_input(
                "Search", placeholder="Author, action, detail…", key="audit_search"
            )
    return outcome, int(limit), search


def _recent_card(frame: pd.DataFrame) -> None:
    with shell.card("audit-recent"):
        shell.section("Most recent actions", "The last five entries of the journal.")
        if frame.empty:
            states.empty_state("Nothing recent", "No entry on this filter.", "clock")
            return

        cards.feed([
            FeedItem(
                title=_label_action(entry.get("action") or "—"),
                message=f"{entry.get('auteur') or '—'} — "
                        f"{entry.get('details') or _label_outcome(entry.get('resultat', ''))}",
                timestamp=fmt_datetime(entry.get("horodatage")),
                tone=AUDIT_OUTCOME_TONES.get(entry.get("resultat", ""), "critical"),
                tag=_label_outcome(entry.get("resultat", "")),
            )
            for entry in frame.head(5).to_dict("records")
        ])


def _table_card(frame: pd.DataFrame, total_loaded: int, search: str) -> None:
    with shell.card("audit-table"):
        shell.section(
            "Full journal",
            "One line per privileged call: author, role, action, outcome and "
            "what the run produced.",
            aside=f"{fmt_int(len(frame))} / {fmt_int(total_loaded)} entries",
        )
        if frame.empty:
            states.empty_state("No result", f"No entry matches \"{search}\".", "search")
            return

        # The stored values stay French in the database; only what is read on
        # screen is translated, exactly as for the work-order statuses.
        display = frame.copy()
        if "resultat" in display:
            display["resultat"] = display["resultat"].map(_label_outcome)
        if "action" in display:
            display["action"] = display["action"].map(_label_action)

        columns = [c for c in ("horodatage", "auteur", "role", "action",
                               "resultat", "details")
                   if c in display.columns]
        tables.data_table(
            display,
            key="audit_table",
            height=460,
            columns=columns,
            config={
                "horodatage": tables.datetime_col("horodatage"),
                "auteur": tables.text_col("auteur", "small"),
                "role": tables.text_col("role", "small"),
                "action": tables.text_col("action", "medium"),
                "resultat": tables.text_col("resultat", "small"),
                "details": tables.text_col("details", "large"),
            },
        )
        tables.export_button(display, "netverify_journal_actions.csv", "audit_export")
