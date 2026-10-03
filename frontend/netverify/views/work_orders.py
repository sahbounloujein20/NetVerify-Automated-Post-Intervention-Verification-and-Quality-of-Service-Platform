"""Work orders — operational workflow follow-up and D+14 control trigger."""

from __future__ import annotations

import streamlit as st

from .. import api, auth
from ..settings import (
    VERIFICATION_DELAY_DAYS,
    STATUS_LABELS,
    STATUSES,
    N8N_WEBHOOK_URL,
    TIMEOUT_N8N,
)
from ..utils import (
    fmt_datetime,
    fmt_int,
    ratio,
    search_frame,
    technologie_de,
    to_frame,
)
from ..ui import cards, shell, states, tables
from ..ui.cards import FeedItem, Tile

# Keys are the values stored in `etat_ot`.
STATUS_TONE = {"Traite": "good", "En cours": "warning", "Emis": "brand"}


def render() -> None:
    shell.render_page_header(
        "Work orders",
        "Follow-up of the work orders, from issue through to the compliance "
        f"control performed {VERIFICATION_DELAY_DAYS} days after closure.",
        "inbox",
    )

    _kpi_row()
    shell.spacer(10)
    _action_bar()
    shell.spacer(10)

    status, fsi, limit, search = _filters()
    result = api.get("/work-orders", etat_ot=status, fsi=fsi, limit=limit)

    with shell.card("rec-table"):
        if result.failed:
            states.error_state(result, "the work orders")
            return

        frame = to_frame(result.list())
        if frame.empty:
            states.empty_state(
                "No work order",
                "No work order matches the selected filters.",
            )
            return

        filtered = search_frame(frame, search).reset_index(drop=True)
        shell.section(
            "Work orders",
            "Select a row to display its details and its control journal.",
            aside=f"{fmt_int(len(filtered))} / {fmt_int(len(frame))} work orders",
        )

        if filtered.empty:
            states.empty_state("No result", f"No work order matches \"{search}\".", "search")
            return

        display_frame = tables.prettify_status(filtered)
        columns = [
            c for c in (
                "ref_demande", "num_appel", "fsi", "debit", "type_demande",
                "type_ot", "etat_ot", "id_technicien", "date_etat",
            ) if c in display_frame.columns
        ]
        selection = tables.data_table(
            display_frame,
            key="rec_table",
            height=470,
            columns=columns,
            config={
                "ref_demande": tables.text_col("ref_demande", "medium"),
                "num_appel": tables.text_col("num_appel", "small"),
                "fsi": tables.text_col("fsi", "small"),
                "debit": tables.text_col("debit", "small"),
                "etat_ot": tables.text_col("etat_ot", "small"),
                "date_etat": tables.datetime_col("date_etat"),
            },
            selectable=True,
        )
        tables.export_button(display_frame, "netverify_reclamations.csv", "rec_export")

    row = tables.selected_row(selection, filtered)
    if row is not None:
        shell.spacer(10)
        _work_order_sheet(row)


# ══════════════════════════════════════════════════════════════════════════════

def _kpi_row() -> None:
    kpis = api.get("/stats/kpis").dict()
    statuses = to_frame(api.get("/stats/by-status").list(), numeric=("nb",))
    by_status = dict(zip(statuses.get("etat_ot", []), statuses.get("nb", []))) if not statuses.empty else {}

    total = kpis.get("total_reclamations", 0)
    processed = kpis.get("total_traitees", 0)

    cards.tile_row([
        Tile(label="Total", value=fmt_int(total), icon="inbox", note="Work orders"),
        Tile(
            label=STATUS_LABELS["Emis"], value=fmt_int(by_status.get("Emis", 0)),
            icon="file", note="Awaiting assignment",
        ),
        Tile(
            label=STATUS_LABELS["En cours"], value=fmt_int(by_status.get("En cours", 0)),
            icon="clock", tone="warning", note="Intervention engaged",
        ),
        Tile(
            label=STATUS_LABELS["Traite"], value=fmt_int(processed),
            icon="check", tone="good", note=f"{ratio(processed, total):.1f} % of the portfolio",
        ),
        Tile(
            label=f"To verify D+{VERIFICATION_DELAY_DAYS}",
            value=fmt_int(kpis.get("reclamations_a_verifier", 0)),
            icon="target", tone="warning", note="Eligible for the control",
        ),
    ])


def _trigger_verification() -> tuple[api.Result, bool]:
    """Runs the D+14 control and says whether it went through n8n.

    The normal route is the n8n webhook: automatic retries, a trace in the
    execution history and the anomaly e-mail, exactly like the scheduled 06:00
    trigger. If n8n is switched off or its workflow inactive, no processing has
    started: the backend is then called directly so the interface stays usable,
    with only the notifications missing. A failure that occurred *during* the
    workflow, on the other hand, is never replayed, on pain of duplicating the
    verification logs.
    """
    if not N8N_WEBHOOK_URL:
        return api.post("/verification/run"), False

    response = api.post_url(N8N_WEBHOOK_URL, timeout=TIMEOUT_N8N)
    if response.unreachable:
        return api.post("/verification/run"), False

    # The backend gave way: n8n answered 200 while relaying the error, and has
    # already sent the failure alert. We simply display the reason.
    reason = response.dict().get("error")
    if response.ok and reason is not None:
        message = reason.get("message", reason) if isinstance(reason, dict) else reason
        return api.Result(data=None, ok=False, error=str(message)), True

    return response, True


def _verification_summary(data: dict, via_n8n: bool) -> str:
    """Report of the control — n8n returns the detail, the backend a message."""
    if "nb_anomalies" not in data:
        return data.get("message", "Verification completed.")

    anomalies = data["nb_anomalies"]
    verified = anomalies + data.get("nb_conformes", 0) + data.get("nb_sans_mesure", 0)
    if not anomalies:
        return f"{verified} work order(s) verified, no anomaly."

    summary = f"{anomalies} anomaly(ies) out of {verified} work order(s) verified"
    return f"{summary} — e-mail sent." if via_n8n else f"{summary}."


def _action_bar() -> None:
    with shell.card("rec-action"):
        text, button = st.columns([3, 1], vertical_alignment="center")
        with text:
            st.html(
                f"""
                <div>
                  <div style="font-size:15px;font-weight:750;color:var(--text)">
                    D+{VERIFICATION_DELAY_DAYS} compliance control</div>
                  <div style="font-size:13px;color:var(--muted);margin-top:5px;line-height:1.5">
                    Compares the measured rate with the subscribed rate for every intervention
                    closed more than {VERIFICATION_DELAY_DAYS} days ago and journals the gaps detected.
                  </div>
                </div>
                """
            )
        with button:
            # The backend already refuses the call from a technician (403). The
            # button is nonetheless disabled here: letting the click through only
            # to show a refusal would be a dead end, whereas the tooltip says
            # what to do.
            allowed = auth.is_supervisor()
            if st.button("Run the verification", type="primary", width="stretch",
                         icon=":material/play_arrow:", key="rec_verif",
                         disabled=not allowed,
                         help=None if allowed else
                              "Restricted to supervisors. The automatic 06:00 "
                              "control stays active for everyone."):
                with st.spinner("Verification in progress…"):
                    response, via_n8n = _trigger_verification()
                if response.ok:
                    st.toast(_verification_summary(response.dict(), via_n8n), icon="✅")
                    st.rerun()
                else:
                    st.toast(f"Failed: {response.error}", icon="⚠️")


def _filters() -> tuple[str, str, int, str]:
    isps = to_frame(api.get("/stats/by-isp").list())
    isp_options = ["All", *sorted(isps["fsi"].dropna().unique())] if "fsi" in isps.columns else ["All"]

    with shell.card("rec-filtres"):
        col1, col2, col3, col4 = st.columns([1, 1, 1, 2], vertical_alignment="bottom")
        with col1:
            status = st.selectbox(
                "Status", ["All", *STATUSES], key="rec_etat",
                format_func=lambda e: STATUS_LABELS.get(e, e),
            )
        with col2:
            fsi = st.selectbox("ISP", isp_options, key="rec_fsi")
        with col3:
            limit = st.number_input("Work orders loaded", 25, 500, 200, step=25, key="rec_limit")
        with col4:
            search = st.text_input(
                "Search", placeholder="Reference, line number, technician…", key="rec_search"
            )
    return status, fsi, int(limit), search


def _work_order_sheet(row) -> None:
    reference = str(row.get("ref_demande", ""))
    status = str(row.get("etat_ot", ""))
    tone = STATUS_TONE.get(status, "neutral")

    with shell.card("rec-detail"):
        shell.section(
            f"Work order {reference}",
            "Context of the intervention and the associated control journal.",
            aside=technologie_de(reference),
        )
        st.html(
            cards.badge(STATUS_LABELS.get(status, status or "—"), tone)
            + cards.badge(f"ISP {row.get('fsi') or '—'}", "neutral", dot=False)
            + cards.badge(f"Technician {row.get('id_technicien') or 'unassigned'}", "neutral", dot=False)
        )
        shell.spacer(12)

        shell.key_values([
            ("Customer line", row.get("num_appel") or "—"),
            ("Subscribed rate", row.get("debit") or "—"),
            ("Request type", row.get("type_demande") or "—"),
            ("Work-order type", row.get("type_ot") or "—"),
            ("Status date", fmt_datetime(row.get("date_etat"))),
            ("Intervention site", row.get("position_site_nouvelle") or "—"),
            ("Zone", row.get("zone") or "—"),
        ])

        shell.spacer(14)
        _journal(reference)


def _journal(reference: str) -> None:
    """Control journal of the work order.

    The backend exposes no filter by reference (and a reference contains "/",
    which is impractical in a URL segment): the filtering is done client-side on
    the journal that is already loaded and cached.
    """
    result = api.get("/logs", limit=500)
    if result.failed:
        states.error_state(result, "the control journal")
        return

    frame = to_frame(result.list())
    if frame.empty or "ref_demande" not in frame.columns:
        states.empty_state("No control", "This work order has not been controlled yet.", "shield")
        return

    rows = frame[frame["ref_demande"] == reference]
    if rows.empty:
        states.empty_state(
            "No gap recorded",
            "No anomaly has been journalled for this work order.",
            "shield",
        )
        return

    st.html('<div class="legend-note" style="margin-bottom:8px">Control journal</div>')
    cards.feed([
        FeedItem(
            title=entry.get("statut_test", "—"),
            message=entry.get("message_log") or "—",
            timestamp=fmt_datetime(entry.get("date_test")),
            tone="critical" if entry.get("statut_test") == "ANOMALIE" else "good",
            tag=f"#{entry.get('id_log', '')}",
        )
        for entry in rows.to_dict("records")
    ])
