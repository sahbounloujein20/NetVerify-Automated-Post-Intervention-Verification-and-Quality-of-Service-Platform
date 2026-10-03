"""Operational performance — work-order stock, daily flow and root causes.

Four operational questions, in the order in which they arise:

1. **Is the stock ageing?** Age of the unclosed work orders, per band.
2. **Is the flow degrading?** Daily volume smoothed over 7 days.
3. **Where does the problem concentrate?** Provider x technology matrix.
4. **What should be fixed first?** Pareto of the anomaly root causes.

Age is counted from the most recent observation date in the referential, and
not from the current clock: the extract is frozen, and measured against today
the entire stock would tip into the oldest band and the chart would stop
teaching anything. The reference date is written under the chart.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import api, theme
from ..settings import TECHNOLOGIES
from ..utils import fmt_datetime, fmt_int, fmt_pct, ratio, to_frame
from ..ui import cards, charts, shell, states
from ..ui.cards import Tile

# Reading order of the age bands — freshest to oldest. These strings must match
# the labels produced by `/stats/ops/backlog` in Backend/analytics.py.
ORDRE_TRANCHES = ["0-7 d", "8-14 d", "15-30 d", "30 d and over"]

# Cumulative share beyond which the bulk of the volume is considered covered.
PARETO_THRESHOLD = 80.0


def render() -> None:
    shell.render_page_header(
        "Operational performance",
        "Age of the intervention stock, daily flow, concentration per provider "
        "and hierarchy of the anomaly causes.",
        "target",
    )

    backlog = api.get("/stats/ops/backlog")
    flows = api.get("/stats/ops/daily-flow")

    if backlog.failed and flows.failed:
        states.offline_banner()

    _kpi_row(backlog.dict(), flows.list())
    shell.spacer(12)

    left, right = st.columns([1, 1.15], gap="medium")
    with left:
        _backlog_card(backlog)
    with right:
        _flux_card(flows)

    shell.spacer(12)
    bottom_left, bottom_right = st.columns([1, 1.1], gap="medium")
    with bottom_left:
        _matrice_card()
    with bottom_right:
        _pareto_card()


# ══════════════════════════════════════════════════════════════════════════════

def _kpi_row(backlog: dict, flows: list[dict]) -> None:
    tuiles = []

    if backlog:
        stock = backlog.get("total", 0)
        tuiles.append(Tile(
            label="Open stock",
            value=fmt_int(stock),
            icon="inbox",
            tone="warning" if stock else "good",
            note="Work orders unclosed at the reference date",
        ))
        tuiles.append(Tile(
            label="Median age",
            value=f"{backlog.get('age_median', 0):g}".replace(".", ","),
            unit="d",
            icon="clock",
            tone="critical" if backlog.get("age_median", 0) > 14 else "warning",
            note=f"Average {backlog.get('age_moyen', 0):g} d · "
                 f"maximum {backlog.get('age_max', 0):g} d".replace(".", ","),
        ))

        tranches = to_frame(backlog.get("tranches", []), numeric=("total",))
        if not tranches.empty:
            anciennes = int(
                tranches[tranches["tranche"].isin(["15-30 d", "30 d and over"])]["total"].sum()
            )
            part = ratio(anciennes, backlog.get("total", 0))
            tuiles.append(Tile(
                label="Stock older than 14 days",
                value=fmt_pct(part, 1).rstrip("%"),
                unit="%",
                icon="alert",
                tone="critical" if part > 40 else "warning" if part else "good",
                note=f"{fmt_int(anciennes)} work orders past the verification delay",
            ))

    frame = to_frame(flows, numeric=("total", "traitees", "moyenne_mobile_7j"))
    if not frame.empty:
        tuiles.append(Tile(
            label="Average daily volume",
            value=f"{frame['total'].mean():.1f}".replace(".", ","),
            icon="activity",
            note=f"Over {fmt_int(len(frame))} days observed",
            trend=frame["total"].tolist(),
        ))
        rate = ratio(frame["traitees"].sum(), frame["total"].sum())
        tuiles.append(Tile(
            label="Share closed over the period",
            value=fmt_pct(rate, 1).rstrip("%"),
            unit="%",
            icon="check",
            tone=theme.status_of(rate),
            meter=(rate, 100),
        ))

    if tuiles:
        cards.tile_row(tuiles)


def _backlog_card(result) -> None:
    with shell.card("ops-backlog", height="stretch"):
        shell.section(
            "Age of the open stock",
            "\"Issued\" and \"In progress\" work orders, split by age band.",
        )
        if result.failed:
            states.error_state(result, "the age of the stock")
            return

        data = result.dict()
        tranches = to_frame(
            data.get("tranches", []), numeric=("total", "emises", "en_cours", "age_moyen")
        )
        if tranches.empty:
            states.empty_state(
                "No open work order",
                "Every intervention in the referential is closed.",
                "check",
            )
            return

        tranches["rang"] = tranches["tranche"].map(
            lambda t: ORDRE_TRANCHES.index(t) if t in ORDRE_TRANCHES else 99
        )
        tranches = tranches.sort_values("rang")

        shell.legend([
            (theme.STATUS_COLORS["Emis"], "Issued", "bar"),
            (theme.STATUS_COLORS["En cours"], "In progress", "bar"),
        ], note="Total height: stock of the band")

        figure = charts.stacked_columns(
            tranches["tranche"],
            [
                ("Issued", tranches["emises"], theme.STATUS_COLORS["Emis"]),
                ("In progress", tranches["en_cours"], theme.STATUS_COLORS["En cours"]),
            ],
            total_label=False,
        )
        figure.update_layout(showlegend=False)
        charts.show(figure, height=300, key="ops_backlog")

        shell.caption(
            "Age counted from the most recent observation date in the "
            f"referential ({fmt_datetime(data.get('date_reference'), with_time=False)}), "
            "and not from today."
        )

        charts.table_twin(
            tranches[["tranche", "total", "emises", "en_cours", "age_moyen"]].rename(columns={
                "tranche": "Band", "total": "Total", "emises": "Issued",
                "en_cours": "In progress", "age_moyen": "Average age (d)",
            })
        )


def _flux_card(result) -> None:
    with shell.card("ops-flux", height="stretch"):
        shell.section(
            "Daily flow of status changes",
            "Raw volume and trend smoothed over a rolling 7 days.",
            accent="cyan",
        )
        if not states.guard(result, "the daily flow"):
            return

        frame = to_frame(result.list(), numeric=("total", "traitees", "moyenne_mobile_7j"))
        frame["libelle"] = pd.to_datetime(frame["jour"], errors="coerce").dt.strftime("%d/%m")

        # The first six points of a 7-day moving average are computed over an
        # incomplete window: plotting them like the rest of the curve would
        # assert a trend that does not yet have its points.
        complet = frame[~frame["partiel"].astype(bool)] if "partiel" in frame.columns else frame

        shell.legend([
            (theme.SERIES[0], "Daily volume", "bar"),
            (theme.SERIES[1], "7-day moving average", "bar"),
        ], note=f"{fmt_int(len(frame))} days observed")

        figure = charts.columns(frame["libelle"], frame["total"])
        figure.update_traces(text=None, marker=dict(color=theme.SERIES[0], cornerradius=3))
        figure.add_scatter(
            x=complet["libelle"],
            y=complet["moyenne_mobile_7j"],
            mode="lines",
            name="7-day moving average",
            line=dict(color=theme.SERIES[1], width=2, shape="spline", smoothing=0.4),
            hovertemplate="7-day average: %{y}<extra></extra>",
        )
        figure.update_layout(showlegend=False, bargap=0.35)
        charts.show(figure, height=300, key="ops_flux")

        charts.table_twin(
            frame[["libelle", "total", "traitees", "moyenne_mobile_7j"]].rename(columns={
                "libelle": "Day", "total": "Status changes",
                "traitees": "Closures", "moyenne_mobile_7j": "7-day average",
            })
        )


def _matrice_card() -> None:
    result = api.get("/stats/ops/isp-technology-matrix")

    with shell.card("ops-matrice", height="stretch"):
        shell.section(
            "Resolution rate — provider x technology",
            "Crossing of the two axes of responsibility. The hue carries the "
            "rate, the value is written in every cell.",
        )
        if not states.guard(result, "the provider x technology matrix"):
            return

        frame = to_frame(result.list(), numeric=("total", "traitees", "taux_resolution"))

        # Client-side pivot: the API returns the cells flat so as not to depend
        # on the ISP referential of the day.
        matrice = frame.pivot_table(
            index="fsi", columns="technologie", values="taux_resolution", aggfunc="first"
        )
        effectifs = frame.pivot_table(
            index="fsi", columns="technologie", values="total", aggfunc="first"
        )

        columns = [t for t in TECHNOLOGIES if t in matrice.columns]
        matrice = matrice[columns]
        effectifs = effectifs.reindex(columns=columns)

        texts = [
            [
                "—" if pd.isna(value) else f"{value:.0f} %"
                for value in row
            ]
            for row in matrice.to_numpy()
        ]

        figure = charts.heatmap(
            matrice.columns.tolist(),
            matrice.index.tolist(),
            matrice.fillna(0).to_numpy().tolist(),
            texts=texts,
            unit=" %",
            scale_title="Resolution",
        )
        charts.show(figure, height=300, key="ops_matrice")

        detail = frame[["fsi", "technologie", "total", "traitees", "taux_resolution"]]
        charts.table_twin(detail.rename(columns={
            "fsi": "ISP", "technologie": "Technology", "total": "Work orders",
            "traitees": "Closed", "taux_resolution": "Resolution (%)",
        }))

        faible = frame.loc[frame["taux_resolution"].idxmin()] if not frame.empty else None
        if faible is not None:
            shell.caption(
                f"Lowest cell: {faible['fsi']} on {faible['technologie']} — "
                f"{faible['taux_resolution']:g} % over {fmt_int(faible['total'])} work orders."
                .replace(".", ",")
            )


def _pareto_card() -> None:
    result = api.get("/stats/ops/pareto-of-causes")

    with shell.card("ops-pareto", height="stretch"):
        shell.section(
            "Root causes of the anomalies",
            "Ranked by volume and cumulative share. An anomaly is counted "
            "against its physical cause when the diagnosis identified one, not "
            "against the observed symptom.",
            accent="cyan",
        )
        if not states.guard(result, "the anomaly causes",
                            title="No anomaly",
                            message="No gap has been journalled by the D+14 control."):
            return

        frame = to_frame(result.list(), numeric=("nb", "part", "cumul"))

        shell.legend([
            (theme.SERIES[0], "Share of the cause", "bar"),
            (theme.SERIES[1], "Cumulative share", "diamond"),
        ], note=f"{fmt_int(frame['nb'].sum())} anomalies classified")

        # The full labels are long; the axis receives a short form while the
        # tooltip and the table keep the whole heading.
        courts = frame["cause"].map(_short_label)

        figure = charts.pareto(courts, frame["part"], frame["cumul"], threshold=PARETO_THRESHOLD)
        figure.update_layout(showlegend=False)
        charts.show(figure, height=300, key="ops_pareto")

        dominante = frame.iloc[0]
        shell.caption(
            f"On its own, \"{dominante['cause']}\" accounts for "
            f"{fmt_pct(dominante['part'], 1)} of the journalled anomalies."
        )

        charts.table_twin(frame[["cause", "nb", "part", "cumul"]].rename(columns={
            "cause": "Root cause", "nb": "Anomalies",
            "part": "Share (%)", "cumul": "Cumulative (%)",
        }))


def _short_label(cause: str) -> str:
    """Removes the parenthesised precision so it fits on the axis."""
    text = str(cause or "")
    return text.split(" (")[0].strip() or text
