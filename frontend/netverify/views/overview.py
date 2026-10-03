"""Dashboard — home page, reusing the original composition."""

from __future__ import annotations

import streamlit as st

from .. import api, theme
from ..settings import VERIFICATION_DELAY_DAYS, STATUS_LABELS, MONTH_LABELS
from ..utils import fmt_datetime, fmt_int, fmt_pct, ratio, to_frame, variation
from ..ui import cards, charts, shell, states
from ..ui.cards import FeedItem, Tile


def render() -> None:
    kpis = api.get("/stats/kpis")
    evolution = api.get("/stats/monthly-trend")

    if kpis.failed and evolution.failed:
        states.offline_banner()

    _kpi_row(kpis.dict(), evolution.list())

    shell.spacer(18)
    left, right = st.columns([2, 1], gap="medium")
    with left:
        _compliance_card(evolution)
    with right:
        _alerts_card()

    shell.spacer(18)
    col1, col2, col3 = st.columns(3, gap="medium")
    with col1:
        _technologies_card()
    with col2:
        _statuses_card()
    with col3:
        _fsi_card()


# ══════════════════════════════════════════════════════════════════════════════

def _kpi_row(kpis: dict, evolution: list[dict]) -> None:
    total = kpis.get("total_reclamations", 0)
    processed = kpis.get("total_traitees", 0)
    anomalies = kpis.get("total_anomalies", 0)
    clients = kpis.get("total_clients", 0)
    to_verify = kpis.get("reclamations_a_verifier", 0)
    rate = ratio(processed, total)

    # The changes come from the real monthly history: without history, no change
    # is displayed rather than an invented comparison.
    frame = to_frame(evolution, numeric=("total", "traitees", "en_cours", "emises"))
    tendance, delta_volume, rate_delta = [], None, None
    if not frame.empty:
        tendance = frame["total"].tolist()
        if len(frame) >= 2:
            latest, precedent = frame.iloc[-1], frame.iloc[-2]
            delta_volume = variation(latest["total"], precedent["total"])
            rate_delta = variation(
                ratio(latest["traitees"], latest["total"]),
                ratio(precedent["traitees"], precedent["total"]),
            )

    cards.tile_row([
        Tile(
            label="Work orders",
            value=fmt_int(total),
            icon="inbox",
            delta=delta_volume,
            delta_up_is_good=False,
            note="vs previous month" if delta_volume is not None else "Cumulative volume",
            trend=tendance,
        ),
        Tile(
            label="Resolution rate",
            value=fmt_pct(rate, 1).rstrip("%"),
            unit="%",
            icon="check",
            tone=theme.status_of(rate),
            delta=rate_delta,
            note="vs previous month" if rate_delta is not None else f"{fmt_int(processed)} processed",
            meter=(rate, 100),
        ),
        Tile(
            label="Supervised customers",
            value=fmt_int(clients),
            icon="users",
            note="Connected estate under supervision",
        ),
        Tile(
            label=f"D+{VERIFICATION_DELAY_DAYS} queue",
            value=fmt_int(to_verify),
            icon="clock",
            tone="warning" if to_verify else "good",
            note="Interventions awaiting control",
        ),
        Tile(
            label="Anomalies",
            value=fmt_int(anomalies),
            icon="alert",
            tone="critical" if anomalies else "good",
            note="Compliance gaps recorded",
        ),
    ])


def _compliance_card(result) -> None:
    with shell.card("evolution", height="stretch"):
        shell.section(
            "Compliance overview",
            "Work orders per month, broken down by status. The total height of "
            "the area gives the volume of the month.",
        )
        if not states.guard(result, "the monthly history",
                            title="History unavailable",
                            message="No dated work order has been recorded yet."):
            return

        frame = to_frame(result.list(), numeric=("total", "traitees", "en_cours", "emises"))
        frame["libelle"] = frame["mois"].map(_short_month)

        shell.legend([
            (theme.STATUS_COLORS["Traite"], "Processed", "bar"),
            (theme.STATUS_COLORS["En cours"], "In progress", "bar"),
            (theme.STATUS_COLORS["Emis"], "Issued", "bar"),
        ], note="Annotated value: total of the last month")

        figure = charts.stacked_area(
            frame["libelle"],
            [
                ("Processed", frame["traitees"], theme.STATUS_COLORS["Traite"]),
                ("In progress", frame["en_cours"], theme.STATUS_COLORS["En cours"]),
                ("Issued", frame["emises"], theme.STATUS_COLORS["Emis"]),
            ],
        )
        figure.update_layout(showlegend=False)
        charts.show(figure, height=318, key="ov_evolution")

        table = frame[["libelle", "total", "traitees", "en_cours", "emises"]].rename(
            columns={"libelle": "Month", "total": "Total", "traitees": "Processed",
                     "en_cours": "In progress", "emises": "Issued"}
        )
        charts.table_twin(table)


def _alerts_card() -> None:
    result = api.get("/logs", limit=6)
    with shell.card("alertes", height="stretch"):
        shell.section("Latest alerts", "Most recent verification journal.", accent="cyan")
        if result.failed:
            states.error_state(result, "the anomaly journal")
            return
        if result.empty:
            states.empty_state(
                "No alert",
                "No compliance gap has been recorded over the period.",
                "shield",
            )
            return

        cards.feed([
            FeedItem(
                title=entry.get("ref_demande") or "—",
                message=entry.get("message_log") or "No diagnosis recorded.",
                timestamp=fmt_datetime(entry.get("date_test")),
                tone="critical" if entry.get("statut_test") == "ANOMALIE" else "good",
                # "ANOMALIE" is the value stored in `statut_test`; the tag shown
                # to the operator is in English.
                tag="ANOMALY" if entry.get("statut_test") == "ANOMALIE" else "COMPLIANT",
            )
            for entry in result.list()
        ])


def _technologies_card() -> None:
    result = api.get("/stats/anomalies-by-technology")
    with shell.card("techno", height="stretch"):
        shell.section("By technology", "Work orders according to the reference prefix.")
        if not states.guard(result, "the breakdown by technology"):
            return

        frame = to_frame(result.list(), numeric=("nb_anomalies",)).sort_values(
            "nb_anomalies", ascending=False
        )
        # A single series: a single hue. v1 gave three different blues to three
        # bars that carry no distinct identity whatsoever.
        figure = charts.columns(frame["technologie"], frame["nb_anomalies"])
        charts.show(figure, height=250, key="ov_techno")
        charts.table_twin(
            frame.rename(columns={"technologie": "Technology", "nb_anomalies": "Work orders"})
        )


def _statuses_card() -> None:
    result = api.get("/stats/by-status")
    with shell.card("etats", height="stretch"):
        shell.section("By status", "Current position of the portfolio.")
        if not states.guard(result, "the breakdown by status"):
            return

        frame = to_frame(result.list(), numeric=("nb",))
        # The values are those stored in `etat_ot`; STATUS_LABELS turns them
        # into the English wording shown on screen.
        order = ["Traite", "En cours", "Emis"]
        frame["rank"] = frame["etat_ot"].map(lambda e: order.index(e) if e in order else 99)
        frame = frame.sort_values("rank")

        total = int(frame["nb"].sum())
        labels = [STATUS_LABELS.get(e, e) for e in frame["etat_ot"]]
        colours = [theme.STATUS_COLORS.get(e, theme.INK_3) for e in frame["etat_ot"]]

        figure = charts.donut(labels, frame["nb"], colours,
                              center_value=fmt_int(total), center_label="work orders")
        charts.show(figure, height=196, key="ov_etats")

        shell.legend([
            (colour, f"{label} · {fmt_int(value)} ({ratio(value, total):.0f} %)", "dot")
            for colour, label, value in zip(colours, labels, frame["nb"])
        ])

        table = frame[["etat_ot", "nb"]].copy()
        table["etat_ot"] = labels
        table["part"] = [f"{ratio(v, total):.1f} %" for v in frame["nb"]]
        charts.table_twin(table.rename(columns={"etat_ot": "Status", "nb": "Work orders", "part": "Share"}))


def _fsi_card() -> None:
    result = api.get("/stats/by-isp")
    with shell.card("fsi", height="stretch"):
        shell.section("By ISP", "Most solicited providers.")
        if not states.guard(result, "the breakdown by ISP"):
            return

        frame = to_frame(result.list(), numeric=("nb_reclamations",))
        frame = frame.sort_values("nb_reclamations", ascending=True).tail(6)
        figure = charts.ranked_bars(frame["fsi"], frame["nb_reclamations"])
        charts.show(figure, height=250, key="ov_fsi")
        charts.table_twin(
            frame.sort_values("nb_reclamations", ascending=False)
            .rename(columns={"fsi": "ISP", "nb_reclamations": "Work orders"})
        )


def _short_month(code) -> str:
    """"2026-07" -> "Jul 26" (the axis stays readable over 12+ points)."""
    text = str(code or "")
    if len(text) == 7 and text[4] == "-":
        return f"{MONTH_LABELS.get(text[5:7], text[5:7])} {text[2:4]}"
    return text
