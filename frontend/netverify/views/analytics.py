"""Analytics — rate gaps and performance of the intervention teams.

Reserved for supervisors, and the only page in that position along with the
audit trail: it names the field agents and ranks them, which is management data
rather than operational data. A technician does not reach it — it is not even
mounted in their navigation — and reads their own figures on "My results"
instead, where the team appears only as an anonymous benchmark. The two
`by-technician` endpoints refuse them independently, in case the page is called
by any other route.
"""

from __future__ import annotations

import streamlit as st

from .. import api, theme
from ..settings import COMPLIANCE_TARGET
from ..utils import fmt_int, fmt_pct, to_frame
from ..ui import cards, charts, shell, states, tables
from ..ui.cards import Tile

KBPS_PER_MBPS = 1024


def render() -> None:
    shell.render_page_header(
        "Analytics",
        "Gap between the subscribed rate and the rate actually measured, and "
        "comparative performance of the technicians. Reserved for supervisors.",
        "chart",
    )

    debits = api.get("/stats/rate-comparison")
    compliance = api.get("/stats/compliance-by-technician")

    _kpi_row(debits, compliance)
    shell.spacer(10)

    left, right = st.columns([1, 1], gap="medium")
    with left:
        _debit_card(debits)
    with right:
        _compliance_card(compliance)

    shell.spacer(10)
    _anomalies_card()


# ══════════════════════════════════════════════════════════════════════════════

def _gaps(debits) -> "tuple":
    """Prepares the table of rate gaps (in Mb/s and in %)."""
    frame = to_frame(debits.list(), numeric=("debit_promis_kbps", "debit_mesure_kbps", "nb_clients"))
    if frame.empty:
        return frame, None
    frame = frame.copy()
    frame["promis_mbps"] = frame["debit_promis_kbps"] / KBPS_PER_MBPS
    frame["mesure_mbps"] = frame["debit_mesure_kbps"] / KBPS_PER_MBPS
    frame["ecart_pct"] = (
        (frame["debit_promis_kbps"] - frame["debit_mesure_kbps"])
        / frame["debit_promis_kbps"].replace(0, 1) * 100
    ).round(1)
    pire = frame.loc[frame["ecart_pct"].idxmax()]
    return frame, pire


def _kpi_row(debits, compliance) -> None:
    frame, pire = _gaps(debits)
    perf = to_frame(compliance.list(), numeric=("taux_conformite", "total", "traitees"))

    tuiles = []

    if not frame.empty:
        average_gap = float(frame["ecart_pct"].mean())
        tuiles.append(Tile(
            label="Average rate gap",
            value=fmt_pct(average_gap, 1).rstrip("%"),
            unit="%",
            icon="gauge",
            tone="critical" if average_gap > 10 else "good",
            note="Subscribed vs measured, all technologies",
        ))
        if pire is not None:
            tuiles.append(Tile(
                label="Most degraded technology",
                value=str(pire["technologie"]),
                icon="alert",
                tone="warning",
                note=f"{pire['ecart_pct']:.1f} % average gap".replace(".", ","),
            ))

    if not perf.empty:
        mean = float(perf["taux_conformite"].mean())
        sous_objectif = int((perf["taux_conformite"] < COMPLIANCE_TARGET).sum())
        tuiles.append(Tile(
            label="Average compliance",
            value=fmt_pct(mean, 1).rstrip("%"),
            unit="%",
            icon="check",
            tone=theme.status_of(mean),
            note=f"Target {COMPLIANCE_TARGET:g} %",
            meter=(mean, COMPLIANCE_TARGET),
        ))
        tuiles.append(Tile(
            label="Technicians below target",
            value=fmt_int(sous_objectif),
            icon="users",
            tone="critical" if sous_objectif else "good",
            note=f"Out of {fmt_int(len(perf))} ranked technicians",
        ))

    if tuiles:
        cards.tile_row(tuiles)


def _debit_card(result) -> None:
    with shell.card("ana-debit", height="stretch"):
        shell.section(
            "Subscribed rate vs measured rate",
            "Averages per technology, on a single scale in Mb/s.",
        )
        if not states.guard(result, "the rate comparison",
                            title="Comparison unavailable",
                            message="No NetScan measurement can be matched with a work order."):
            return

        frame, _ = _gaps(result)
        shell.legend([
            (theme.SERIES[0], "Subscribed rate", "bar"),
            (theme.SERIES[1], "Measured rate", "bar"),
        ], note="Average per technology")

        figure = charts.grouped_columns(
            frame["technologie"],
            [
                ("Subscribed rate", frame["promis_mbps"], theme.SERIES[0]),
                ("Measured rate", frame["mesure_mbps"], theme.SERIES[1]),
            ],
        )
        figure.update_layout(showlegend=False)
        figure.update_yaxes(ticksuffix=" Mb/s")
        figure.update_traces(hovertemplate="%{fullData.name}: %{y:.1f} Mb/s<extra></extra>")
        charts.show(figure, height=306, key="ana_debit")

        table = frame[["technologie", "promis_mbps", "mesure_mbps", "ecart_pct", "nb_clients"]].round(1)
        charts.table_twin(table.rename(columns={
            "technologie": "Technology", "promis_mbps": "Subscribed (Mb/s)",
            "mesure_mbps": "Measured (Mb/s)", "ecart_pct": "Gap (%)",
            # The backend counts work-order x measurement pairs, not distinct
            # lines: the column is named for what it really contains.
            "nb_clients": "Matched measurements",
        }))


def _compliance_card(result) -> None:
    with shell.card("ana-conformite", height="stretch"):
        shell.section(
            "Compliance per technician",
            f"Share of closed interventions. Internal target: {COMPLIANCE_TARGET:g} %.",
        )
        if not states.guard(result, "the technician performance"):
            return

        frame = to_frame(result.list(), numeric=("taux_conformite", "total", "traitees"))
        ranking = frame.sort_values("taux_conformite", ascending=True).tail(12)

        figure = charts.ranked_bars(
            ranking["id_technicien"],
            ranking["taux_conformite"],
            value_suffix=" %",
            target=COMPLIANCE_TARGET,
            axis_max=118,
        )
        charts.show(figure, height=306, key="ana_conformite")

        table = frame.sort_values("taux_conformite", ascending=False)[
            ["id_technicien", "total", "traitees", "taux_conformite"]
        ]
        charts.table_twin(table.rename(columns={
            "id_technicien": "Technician", "total": "Interventions",
            "traitees": "Closed", "taux_conformite": "Compliance (%)",
        }))


def _anomalies_card() -> None:
    result = api.get("/stats/anomalies-by-technician")
    with shell.card("ana-anomalies"):
        shell.section(
            "Anomalies attributed per technician",
            "Number of gaps journalled after control, per field agent.",
        )
        if not states.guard(result, "the anomalies per technician",
                            title="No anomaly",
                            message="No gap has been attributed to a technician."):
            return

        frame = to_frame(result.list(), numeric=("nb_anomalies",))
        chart, detail = st.columns([1.4, 1], gap="medium")

        with chart:
            ranking = frame.sort_values("nb_anomalies", ascending=True).tail(10)
            figure = charts.ranked_bars(
                ranking["id_technicien"], ranking["nb_anomalies"], color=theme.SERIES[1]
            )
            charts.show(figure, height=290, key="ana_anomalies")

        with detail:
            tables.data_table(
                frame.sort_values("nb_anomalies", ascending=False),
                key="ana_anomalies_table",
                height=290,
                columns=["id_technicien", "nb_anomalies"],
                config={
                    "id_technicien": tables.text_col("id_technicien"),
                    "nb_anomalies": tables.number_col("nb_anomalies"),
                },
            )
