"""Customer estate — filterable directory and technical sheet of the latest measurement."""

from __future__ import annotations

import streamlit as st

from .. import api
from ..settings import (
    ATTENUATION_MAX_DB,
    RATE_TOLERANCE,
    SNR_MIN_DB,
    TECHNOLOGIES,
)
from ..utils import esc, fmt_datetime, fmt_int, fmt_mbps, search_frame, to_float, to_frame
from ..ui import cards, shell, states, tables
from ..ui.cards import Tile

ICONES_TECHNO = {"ADSL": "signal", "VDSL": "wifi", "GPON": "zap"}


def render() -> None:
    shell.render_page_header(
        "Customer estate",
        "Directory of the supervised lines. Select a line to consult its latest "
        "NetScan measurement and its compliance verdict.",
        "users",
    )

    _kpi_row()
    shell.spacer(10)

    technology, limit, search = _filters()

    result = api.get("/clients", technology=technology, limit=limit)
    with shell.card("clients-table"):
        if result.failed:
            states.error_state(result, "the customer list")
            return

        frame = to_frame(result.list())
        if frame.empty:
            states.empty_state(
                "No customer",
                "The referential contains no line for this filter.",
                "users",
            )
            return

        filtered = search_frame(frame, search).reset_index(drop=True)
        shell.section(
            "Supervised lines",
            "Clicking a row opens its technical sheet.",
            aside=f"{fmt_int(len(filtered))} / {fmt_int(len(frame))} lines",
        )

        if filtered.empty:
            states.empty_state(
                "No result",
                f"No line matches \"{search}\".",
                "search",
            )
            return

        columns = [c for c in ("num_telephone", "nom_client", "techno_souscrite") if c in filtered.columns]
        selection = tables.data_table(
            filtered,
            key="clients_table",
            height=440,
            columns=columns,
            config={
                "num_telephone": tables.text_col("num_telephone", "small"),
                "nom_client": tables.text_col("nom_client", "large"),
                "techno_souscrite": tables.text_col("techno_souscrite", "small"),
            },
            selectable=True,
        )
        tables.export_button(filtered, "netverify_clients.csv", "clients_export")

    row = tables.selected_row(selection, filtered)
    if row is not None:
        shell.spacer(10)
        _fiche_client(str(row.get("num_telephone", "")))


# ══════════════════════════════════════════════════════════════════════════════

def _kpi_row() -> None:
    kpis = api.get("/stats/kpis").dict()
    breakdown = to_frame(api.get("/stats/by-technology").list(), numeric=("nb_clients",))

    tiles = [Tile(
        label="Supervised customers",
        value=fmt_int(kpis.get("total_clients", 0)),
        icon="users",
        note="Complete referential",
    )]

    by_technology = {}
    if not breakdown.empty and "technology" in breakdown.columns:
        by_technology = dict(zip(breakdown["technology"], breakdown["nb_clients"]))

    for technology in TECHNOLOGIES:
        tiles.append(
            Tile(
                label=technology,
                value=fmt_int(by_technology.get(technology, 0)),
                icon=ICONES_TECHNO.get(technology, "signal"),
                note="Connected lines",
            )
        )
    cards.tile_row(tiles)


def _filters() -> tuple[str, int, str]:
    with shell.card("clients-filtres"):
        col1, col2, col3 = st.columns([1, 1, 2], vertical_alignment="bottom")
        with col1:
            technology = st.selectbox("Technology", ["All", *TECHNOLOGIES], key="cl_techno")
        with col2:
            limit = st.number_input("Lines loaded", 10, 500, 100, step=10, key="cl_limit")
        with col3:
            search = st.text_input(
                "Search", placeholder="Name, phone number…", key="cl_search"
            )
    return technology, int(limit), search


def _fiche_client(numero: str) -> None:
    if not numero:
        return

    detail = api.get(f"/clients/{numero}")
    with shell.card("clients-detail"):
        if detail.failed:
            states.error_state(detail, f"the record of customer {numero}")
            return

        data = detail.dict()
        shell.section(
            f"Technical sheet — {data.get('nom_client', numero)}",
            "Latest NetScan measurement available and compliance verdict.",
            aside=f"Line {numero}",
        )

        shell.key_values([
            ("Customer", data.get("nom_client") or "—"),
            ("Phone number", numero),
            ("Subscribed technology", data.get("techno_souscrite") or "—"),
            ("Work orders", fmt_int(data.get("nb_reclamations", 0))),
        ])

        measurement = data.get("derniere_mesure")
        shell.spacer(12)
        if not measurement:
            states.empty_state(
                "No NetScan measurement",
                "No reading has been collected for this line yet. "
                "Run a one-off measurement from the backend to populate it.",
                "activity",
            )
            return

        _measurement_tiles(measurement, data.get("techno_souscrite"))
        st.html(
            f'<div class="legend-note" style="margin-top:10px">Measured on '
            f"{esc(fmt_datetime(measurement.get('timestamp_mesure')))} · line state: "
            f"{esc(measurement.get('status_training') or 'unknown')}</div>"
        )


def _measurement_tiles(measurement: dict, technology: str | None) -> None:
    """Turns a NetScan measurement into verdicts, with the comparator's thresholds."""
    debit = to_float(measurement.get("channel_rate_kbps"))
    maximum = to_float(measurement.get("max_attainable_rate_kbps"))
    snr = to_float(measurement.get("line_snr_margin_down"))
    attenuation = to_float(measurement.get("line_attenuation_down"))

    tiles = [
        Tile(
            label="Measured rate",
            value=fmt_mbps(debit).replace(" Mb/s", ""),
            unit="Mb/s",
            icon="gauge",
            tone="brand",
            note=f"Max attainable rate {fmt_mbps(maximum)}" if maximum else "Downstream channel",
        ),
        Tile(
            label="SNR margin",
            value=f"{snr:.1f}".replace(".", ",") if snr else "—",
            unit="dB",
            icon="activity",
            tone="critical" if 0 < snr < SNR_MIN_DB else "good" if snr else "brand",
            note=f"Unstable below {SNR_MIN_DB:g} dB",
        ),
        Tile(
            label="Line attenuation",
            value=f"{attenuation:.1f}".replace(".", ",") if attenuation else "—",
            unit="dB",
            icon="signal",
            tone="critical" if attenuation > ATTENUATION_MAX_DB else "good" if attenuation else "brand",
            note=f"Degraded beyond {ATTENUATION_MAX_DB:g} dB",
        ),
    ]

    # The contractual verdict (subscribed rate) is delivered by the comparator on
    # the backend side; here the measurement is placed against the physical
    # potential of the line, with the same 90% tolerance.
    if maximum and debit:
        compliant = debit >= maximum * RATE_TOLERANCE
        tiles.append(
            Tile(
                label="Rate vs potential",
                value=f"{debit / maximum * 100:.0f}",
                unit="%",
                icon="check" if compliant else "alert",
                tone="good" if compliant else "critical",
                note=f"Compliance threshold {RATE_TOLERANCE:.0%}",
            )
        )

    cards.tile_row(tiles)
