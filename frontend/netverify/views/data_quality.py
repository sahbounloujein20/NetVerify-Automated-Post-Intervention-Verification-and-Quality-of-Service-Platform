"""Data quality — observability of the estate that feeds the dashboard.

This page does not judge the quality of the NETWORK, but that of the DATA used
to judge it. It answers five questions that have to be answerable before any
indicator can be believed:

* **Volumetry** — how many rows, and how much weight per table?
* **Freshness** — when was each flow last loaded?
* **Completeness** — which columns are actually populated?
* **Integrity** — do the foreign keys all land on a row?
* **Coherence** — do the referentials speak a single language?

The stance taken: what is empty is shown as empty. Five NetScan columns are
never populated by the current chain, and an indicator built on top of them
would be wrong without ever raising an error. Displaying them at 0 % is the only
way of not using them by accident.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import api, theme
from ..utils import fmt_datetime, fmt_int, fmt_pct, ratio, to_frame
from ..ui import cards, charts, shell, states, tables
from ..ui.cards import FeedItem, Tile

# Beyond this delay, a flow is reported as late (hours).
FRESHNESS_THRESHOLD_H = 48.0

# Below this fill rate, a column is treated as unusable.
COMPLETENESS_THRESHOLD = 95.0

TABLE_LABELS = {
    "clients": "Customers",
    "techniciens": "Technicians",
    "reclamations_workflow": "Work orders",
    "mesures_netscan": "NetScan measurements",
    "logs_followup": "Control journal",
}


def render() -> None:
    shell.render_page_header(
        "Data quality",
        "Volumetry, freshness, completeness, referential integrity and "
        "coherence of the referentials feeding NetVerify.",
        "database",
    )

    result = api.get("/stats/data-quality")
    if result.failed:
        states.offline_banner()
        with shell.card("dq-error"):
            states.error_state(result, "the data quality controls")
        return

    data = result.dict()
    if not data:
        with shell.card("dq-empty"):
            states.empty_state(
                "No control available",
                "The backend returned no control result.",
                "database",
            )
        return

    _kpi_row(data)
    shell.spacer(12)

    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        _completeness_card(data)
    with right:
        _freshness_card(data)

    shell.spacer(12)
    bottom_left, bottom_right = st.columns([1.1, 1], gap="medium")
    with bottom_left:
        _cadence_card(data)
    with bottom_right:
        _integrity_card(data)

    shell.spacer(12)
    _volumetry_card(data)


# ══════════════════════════════════════════════════════════════════════════════

def _kpi_row(data: dict) -> None:
    completeness = to_frame(data.get("completude", []), numeric=("taux", "total", "renseigne"))
    integrity = to_frame(data.get("integrite", []), numeric=("anomalies",))
    freshness = to_frame(data.get("fraicheur", []), numeric=("age_heures",))
    volumetry = to_frame(data.get("volumetrie", []), numeric=("lignes",))
    outliers = to_frame(data.get("aberrations", []), numeric=("anomalies",))

    tiles = []

    if not volumetry.empty:
        tiles.append(Tile(
            label="Supervised rows",
            value=fmt_int(volumetry["lignes"].sum()),
            icon="database",
            note=f"Spread over {len(volumetry)} tables",
        ))

    if not completeness.empty:
        usable = int((completeness["taux"] >= COMPLETENESS_THRESHOLD).sum())
        empty = int((completeness["taux"] == 0).sum())
        overall_rate = ratio(completeness["renseigne"].sum(), completeness["total"].sum())
        tiles.append(Tile(
            label="Overall completeness",
            value=fmt_pct(overall_rate, 1).rstrip("%"),
            unit="%",
            icon="check",
            tone="warning" if overall_rate < COMPLETENESS_THRESHOLD else "good",
            note=f"{usable} columns out of {len(completeness)} above "
                 f"{COMPLETENESS_THRESHOLD:g} %",
            meter=(overall_rate, 100),
        ))
        tiles.append(Tile(
            label="Columns never populated",
            value=fmt_int(empty),
            icon="alert",
            tone="critical" if empty else "good",
            note="No indicator should rely on them",
        ))

    if not integrity.empty and "bloquant" in integrity.columns:
        blocking = integrity[integrity["bloquant"].astype(bool)]
        defects = int(blocking["anomalies"].sum())
        tiles.append(Tile(
            label="Integrity defects",
            value=fmt_int(defects),
            icon="shield",
            tone="critical" if defects else "good",
            note=f"Over {len(blocking)} blocking controls",
        ))

    if not freshness.empty:
        lateness = float(freshness["age_heures"].max())
        tiles.append(Tile(
            label="Most delayed flow",
            value=f"{lateness / 24:.1f}".replace(".", ","),
            unit="d",
            icon="clock",
            tone="critical" if lateness > FRESHNESS_THRESHOLD_H else "good",
            note="Since the last record received",
        ))

    if not outliers.empty:
        total_outliers = int(outliers["anomalies"].sum())
        tiles.append(Tile(
            label="Outlying values",
            value=fmt_int(total_outliers),
            icon="sliders",
            tone="warning" if total_outliers else "good",
            note="Zero rates, negative values, future dates",
        ))

    if tiles:
        cards.tile_row(tiles)


def _completeness_card(data: dict) -> None:
    with shell.card("dq-completude", height="stretch"):
        shell.section(
            "Completeness per column",
            "Share of populated rows, column by column. In red, what no "
            "indicator can be built upon.",
        )
        frame = to_frame(data.get("completude", []), numeric=("taux", "total", "renseigne"))
        if frame.empty:
            states.empty_state("No column monitored", icon_name="database")
            return

        frame = frame.sort_values("taux", ascending=True)
        colours = [
            theme.STATUS["critical"] if rate < COMPLETENESS_THRESHOLD else theme.SERIES[0]
            for rate in frame["taux"]
        ]

        shell.legend([
            (theme.SERIES[0], f"Populated at {COMPLETENESS_THRESHOLD:g} % or more", "bar"),
            (theme.STATUS["critical"], "Incomplete or empty", "bar"),
        ], note="One bar per monitored column")

        figure = charts.ranked_bars(
            frame["colonne"], frame["taux"], value_suffix=" %", axis_max=118,
        )
        figure.update_traces(marker=dict(color=colours, cornerradius=4))
        charts.show(figure, height=430, key="dq_completude")

        charts.table_twin(
            frame[["table", "colonne", "renseigne", "total", "taux"]]
            .sort_values("taux")
            .rename(columns={
                "table": "Table", "colonne": "Column", "renseigne": "Populated",
                "total": "Rows", "taux": "Completeness (%)",
            })
        )

        empty = frame[frame["taux"] == 0]
        if not empty.empty:
            shell.caption(
                f"{len(empty)} columns are never populated by the current "
                f"chain: {', '.join(empty['colonne'].head(5))}"
                + (", …" if len(empty) > 5 else "") + "."
            )


def _freshness_card(data: dict) -> None:
    with shell.card("dq-fraicheur", height="stretch"):
        shell.section(
            "Freshness of the flows",
            f"Delay since the last record received. Alert beyond "
            f"{FRESHNESS_THRESHOLD_H:g} h.",
            accent="cyan",
        )
        flows = data.get("fraicheur", [])
        if not flows:
            states.empty_state("No flow tracked", icon_name="clock")
            return

        items = []
        for entry in flows:
            age = entry.get("age_heures")
            late = age is None or age > FRESHNESS_THRESHOLD_H
            if age is None:
                measure = "No record"
            elif age < 48:
                measure = f"{age:.1f} h ago".replace(".", ",")
            else:
                measure = f"{age / 24:.1f} d ago".replace(".", ",")

            items.append(FeedItem(
                title=entry.get("flux") or "—",
                message=f"Last record: {fmt_datetime(entry.get('latest'))} "
                        f"({measure}).",
                timestamp=entry.get("table", ""),
                tone="critical" if late else "good",
                tag="LATE" if late else "UP TO DATE",
            ))
        cards.feed(items)

        coherence = to_frame(data.get("coherence", []), numeric=("nb",))
        if not coherence.empty:
            shell.spacer(8)
            shell.section(
                "Coherence of the status referential",
                "Vocabulary actually present in `status_training`.",
            )
            total = int(coherence["nb"].sum())
            shell.key_values([
                (str(row["valeur"]), f"{fmt_int(row['nb'])} · {fmt_pct(ratio(row['nb'], total), 1)}")
                for _, row in coherence.iterrows()
            ])
            if len(coherence) > 2:
                shell.caption(
                    "Several labels designate the same line status: the "
                    "measurement producers do not write the same vocabulary. "
                    "Any filter on an exact value would miss part of it."
                )


def _cadence_card(data: dict) -> None:
    with shell.card("dq-cadence", height="stretch"):
        shell.section(
            "NetScan collection cadence",
            "Volume of measurements received per collection day.",
        )
        frame = to_frame(
            data.get("cadence", []), numeric=("nb_mesures", "nb_lignes", "nb_snr")
        )
        if frame.empty:
            states.empty_state("No collection recorded", icon_name="activity")
            return

        frame["libelle"] = pd.to_datetime(frame["jour"], errors="coerce").dt.strftime("%d/%m")

        figure = charts.columns(frame["libelle"], frame["nb_mesures"])
        charts.show(figure, height=250, key="dq_cadence")

        days = len(frame)
        total = int(frame["nb_mesures"].sum())
        maximum = int(frame["nb_mesures"].max())
        shell.caption(
            f"{fmt_int(total)} measurements spread over {days} days only, "
            f"including {fmt_pct(ratio(maximum, total), 1)} on the single busiest "
            "day: the collection runs in catch-up bursts, not as a steady flow."
        )

        charts.table_twin(
            frame[["libelle", "nb_mesures", "nb_lignes", "nb_snr"]].rename(columns={
                "libelle": "Day", "nb_mesures": "Measurements",
                "nb_lignes": "Distinct lines", "nb_snr": "Of which SNR margin",
            })
        )


def _integrity_card(data: dict) -> None:
    with shell.card("dq-integrite", height="stretch"):
        shell.section(
            "Integrity and outlying values",
            "Blocking controls and attention signals. A non-blocking control "
            "may have a business explanation.",
            accent="cyan",
        )

        integrity = to_frame(data.get("integrite", []), numeric=("anomalies",))
        outliers = to_frame(data.get("aberrations", []), numeric=("anomalies",))
        if integrity.empty and outliers.empty:
            states.empty_state("No control executed", icon_name="shield")
            return

        rows = []
        if not integrity.empty:
            for _, row in integrity.iterrows():
                blocking = bool(row.get("bloquant", False))
                anomalies = int(row["anomalies"])
                rows.append({
                    "Control": row["controle"],
                    "Anomalies": anomalies,
                    "Verdict": _verdict(anomalies, blocking),
                })
        if not outliers.empty:
            for _, row in outliers.iterrows():
                anomalies = int(row["anomalies"])
                rows.append({
                    "Control": row["controle"],
                    "Anomalies": anomalies,
                    "Verdict": _verdict(anomalies, blocking=False),
                })

        table = pd.DataFrame(rows)
        tables.data_table(
            table,
            key="dq_integrite_table",
            height=430,
            config={
                "Control": st.column_config.TextColumn("Control", width="large"),
                "Anomalies": st.column_config.NumberColumn("Anomalies", format="%d"),
                "Verdict": st.column_config.TextColumn("Verdict", width="small"),
            },
        )


def _verdict(anomalies: int, blocking: bool) -> str:
    """Verdict spelled out in full — never a colour dot on its own."""
    if anomalies == 0:
        return "Compliant"
    return "To fix" if blocking else "To explain"


def _volumetry_card(data: dict) -> None:
    with shell.card("dq-volumetrie"):
        shell.section(
            "Volumetry of the estate",
            "Number of rows and weight on disk, per table.",
        )
        frame = to_frame(data.get("volumetrie", []), numeric=("lignes",))
        if frame.empty:
            states.empty_state("No table inventoried", icon_name="database")
            return

        frame["libelle"] = frame["table"].map(lambda t: TABLE_LABELS.get(t, t))
        frame = frame.sort_values("lignes", ascending=True)

        chart, detail = st.columns([1.5, 1], gap="medium")
        with chart:
            figure = charts.ranked_bars(frame["libelle"], frame["lignes"])
            charts.show(figure, height=250, key="dq_volumetrie")
        with detail:
            tables.data_table(
                frame.sort_values("lignes", ascending=False)[["libelle", "lignes", "taille"]],
                key="dq_volumetrie_table",
                height=250,
                config={
                    "libelle": st.column_config.TextColumn("Table"),
                    "lignes": st.column_config.NumberColumn("Rows", format="%d"),
                    "taille": st.column_config.TextColumn("Weight", width="small"),
                },
            )
