"""Line quality — distribution of the NetScan physical parameters.

The other pages count work orders; this one describes the 20,000 measurements
used to settle them. Three readings complement each other:

* the **distribution** shows the shape of the estate and what crosses the
  threshold;
* the **percentiles per technology** show the dispersion that an average would
  crush;
* the **diagnostic scatter plot** crosses the two thresholds of the verification
  engine to isolate the physically degraded lines.

The rates displayed are always computed against the population actually
measured, never against the total number of measurements: the SNR margin is only
populated on copper pairs, and reporting its breaches against the 20,000
measurements would divide the rate by three with nothing signalling it.
"""

from __future__ import annotations

import streamlit as st

from .. import api, theme
from ..settings import TECHNOLOGIES
from ..utils import fmt_int, fmt_mbps, fmt_pct, ratio, to_frame
from ..ui import cards, charts, shell, states
from ..ui.cards import Tile

# Metrics offered in the selector: displayed label -> key expected by the API.
METRICS = {
    "Signal-to-noise margin (SNR)": "snr",
    "Line attenuation": "attenuation",
    "Delivery of the subscribed rate": "restitution",
}

# Percentile columns matching each metric, and the associated unit.
PERCENTILES = {
    "snr": ("snr_p10", "snr_p50", "snr_p90", " dB", 1),
    "attenuation": ("attenuation_p10", "attenuation_p50", "attenuation_p90", " dB", 1),
    "restitution": ("debit_p10_kbps", "debit_p50_kbps", "debit_p90_kbps", " Mb/s", 1024),
}

KBPS_PER_MBPS = 1024


def render() -> None:
    shell.render_page_header(
        "Line quality",
        "Distribution of the physical parameters read by NetScan: noise margin, "
        "attenuation and the rate actually delivered.",
        "signal",
    )

    summary_data = api.get("/stats/quality/summary")
    if summary_data.failed:
        states.offline_banner()

    _kpi_row(summary_data.dict())
    shell.spacer(12)

    metric = _metric_selector()

    left, right = st.columns([1.35, 1], gap="medium")
    with left:
        _distribution_card(metric)
    with right:
        _percentiles_card(metric)

    shell.spacer(12)
    _scatter_card()


# ══════════════════════════════════════════════════════════════════════════════

def _kpi_row(summary_data: dict) -> None:
    if not summary_data:
        return

    nb_snr = summary_data.get("nb_snr_evalue", 0)
    nb_att = summary_data.get("nb_attenuation_evaluee", 0)
    nb_profil = summary_data.get("nb_profil_connu", 0)

    part_snr = ratio(summary_data.get("nb_snr_sous_seuil", 0), nb_snr)
    part_att = ratio(summary_data.get("nb_attenuation_haute", 0), nb_att)
    part_sous_profil = ratio(summary_data.get("nb_sous_profil", 0), nb_profil)

    cards.tile_row([
        Tile(
            label="Measurements analysed",
            value=fmt_int(summary_data.get("nb_mesures", 0)),
            icon="database",
            note=f"Over {fmt_int(summary_data.get('nb_lignes', 0))} supervised lines",
        ),
        Tile(
            label="Below the SNR threshold",
            value=fmt_pct(part_snr, 1).rstrip("%"),
            unit="%",
            icon="alert",
            tone="critical" if part_snr > 5 else "good",
            # The denominator is written out: it is what makes the rate checkable.
            note=f"{fmt_int(summary_data.get('nb_snr_sous_seuil', 0))} measurements "
                 f"out of {fmt_int(nb_snr)} evaluated",
        ),
        Tile(
            label="Excessive attenuation",
            value=fmt_pct(part_att, 1).rstrip("%"),
            unit="%",
            icon="gauge",
            tone="critical" if part_att > 10 else "warning" if part_att else "good",
            note=f"Beyond {summary_data.get('seuil_attenuation_db', 40):g} dB",
        ),
        Tile(
            label="Below the subscribed rate",
            value=fmt_pct(part_sous_profil, 1).rstrip("%"),
            unit="%",
            icon="trend-down",
            tone="critical" if part_sous_profil > 10 else "good",
            note=f"Tolerance {summary_data.get('tolerance_debit', 0.9) * 100:g} % of the profile",
        ),
        Tile(
            label="Median measured rate",
            value=fmt_mbps(summary_data.get("debit_median_kbps", 0)).replace(" Mb/s", ""),
            unit="Mb/s",
            icon="zap",
            note=f"{fmt_int(summary_data.get('nb_coupures', 0))} measurements with the line down",
        ),
    ])


def _metric_selector() -> str:
    """A single selector drives the distribution AND the percentiles.

    Two separate selectors would allow an inconsistent state — an SNR histogram
    next to attenuation percentiles — that nothing on screen would signal.
    """
    with shell.card("qual-filtres"):
        col1, _ = st.columns([1.2, 2.8], vertical_alignment="bottom")
        with col1:
            choice = st.selectbox("Metric analysed", list(METRICS), key="qual_metrique")
    return METRICS[choice]


def _distribution_card(metric: str) -> None:
    result = api.get("/stats/quality/distribution", metric=metric)

    with shell.card("qual-distribution", height="stretch"):
        if result.failed:
            shell.section("Distribution", "Spread of the measurements.")
            states.error_state(result, "the distribution of the measurements")
            return

        data = result.dict()
        tiers = to_frame(data.get("paliers", []), numeric=("centre", "nb", "part"))
        if tiers.empty:
            shell.section("Distribution", "Spread of the measurements.")
            states.empty_state(
                "No usable measurement",
                "No value is populated for this metric.",
                "database",
            )
            return

        unit = data.get("unite", "")
        threshold = data.get("seuil")
        direction = data.get("sens", "minimum")
        evaluees = data.get("nb_mesures_evaluees", 0)
        out_of_threshold = data.get("nb_hors_seuil", 0)

        shell.section(
            data.get("libelle", "Distribution"),
            f"{fmt_int(evaluees)} measurements evaluated · mean "
            f"{data.get('mean', 0):g}{unit} · standard deviation "
            f"{data.get('ecart_type', 0):g}{unit}".replace(".", ","),
            aside=f"P10 {data.get('p10', 0):g} · median {data.get('mediane', 0):g} "
                  f"· P90 {data.get('p90', 0):g}{unit}".replace(".", ","),
        )

        cote = "below the" if direction == "minimum" else "beyond the"
        shell.legend(
            [
                (theme.SERIES[0], "Compliant population", "bar"),
                (theme.STATUS["critical"], f"Population {cote} threshold", "bar"),
            ],
            note=f"{fmt_int(out_of_threshold)} measurements out of threshold "
                 f"({fmt_pct(ratio(out_of_threshold, evaluees), 1)})",
        )

        width = None
        if len(tiers) > 1:
            # Columns sized on the real width of the bucket: without this Plotly
            # sizes them from the smallest gap between two centres and leaves
            # holes wherever a bucket is empty.
            width = float(tiers["borne_max"].iloc[0] - tiers["borne_min"].iloc[0])

        figure = charts.histogram(
            tiers["centre"],
            tiers["nb"],
            parts=tiers["part"],
            threshold=threshold,
            direction=direction,
            threshold_label=data.get("seuil_libelle", "Threshold"),
            unit=unit,
            width=width,
        )
        charts.show(figure, height=330, key=f"qual_hist_{metric}")

        table = tiers[["borne_min", "borne_max", "nb", "part"]].rename(columns={
            "borne_min": f"From ({unit.strip() or '—'})",
            "borne_max": f"To ({unit.strip() or '—'})",
            "nb": "Measurements", "part": "Share (%)",
        })
        charts.table_twin(table)


def _percentiles_card(metric: str) -> None:
    result = api.get("/stats/quality/percentiles")

    with shell.card("qual-percentiles", height="stretch"):
        shell.section(
            "Dispersion per technology",
            "P10 – P90 span and median. The gap between the bounds designates "
            "the heterogeneity of the estate, which the average alone would hide.",
        )
        if not states.guard(result, "the percentiles per technology"):
            return

        low_column, mid_column, high_column, unit, divisor = PERCENTILES[metric]
        frame = to_frame(
            result.list(),
            numeric=(low_column, mid_column, high_column, "nb_mesures", "couverture_snr"),
        )

        # The SNR margin does not exist on fibre: GPON has only 2% of populated
        # measurements. Plotting it would put a range computed on 162 points in
        # the middle of two ranges computed on 6,000 — visually equivalent,
        # statistically unrelated.
        if metric == "snr":
            frame = frame[frame["couverture_snr"] >= 50]

        if frame.empty:
            states.empty_state(
                "No eligible technology",
                "No technology has enough populated measurements for this "
                "metric.",
                "database",
            )
            return

        for column in (low_column, mid_column, high_column):
            frame[column] = frame[column] / divisor

        shell.legend([
            (theme.SERIES[0], "P10 – P90 range", "bar"),
            (theme.SERIES[0], "Median", "diamond"),
        ], note="One bar per technology")

        figure = charts.range_bars(
            frame["technologie"],
            frame[low_column],
            frame[mid_column],
            frame[high_column],
            unit=unit,
        )
        charts.show(figure, height=330, key=f"qual_perc_{metric}")

        table = frame[["technologie", "nb_mesures", low_column, mid_column, high_column]]
        charts.table_twin(table.round(1).rename(columns={
            "technologie": "Technology", "nb_mesures": "Measurements",
            low_column: f"P10 ({unit.strip()})",
            mid_column: f"Median ({unit.strip()})",
            high_column: f"P90 ({unit.strip()})",
        }))


def _scatter_card() -> None:
    result = api.get("/stats/quality/scatter")

    with shell.card("qual-nuage"):
        shell.section(
            "Diagnostic scatter plot — attenuation x noise margin",
            "Each point is a measurement. The two hairlines are the thresholds "
            "of the verification engine: the shaded quadrant, bottom right, "
            "gathers the lines that cross both.",
            accent="cyan",
        )
        if not states.guard(result, "the diagnostic scatter plot"):
            return

        data = result.dict()
        points = to_frame(data.get("points", []), numeric=("attenuation", "snr", "debit_kbps"))
        if points.empty:
            states.empty_state(
                "No crossed measurement",
                "No measurement carries both an attenuation and an SNR margin.",
                "chart",
            )
            return

        quadrants = data.get("quadrants", {})
        total = quadrants.get("total", 0)
        seuil_snr = data.get("seuil_snr_db", 6.0)
        seuil_att = data.get("seuil_attenuation_db", 40.0)

        chart, detail = st.columns([1.55, 1], gap="medium")

        with chart:
            # Colour carries the technology — an identity — and not the
            # severity: that is already read from the position of the point
            # against the two thresholds, repainting it would be redundant.
            groups = [
                (technology, subset["attenuation"], subset["snr"], theme.SERIES[index])
                for index, technology in enumerate(TECHNOLOGIES)
                if not (subset := points[points["technologie"] == technology]).empty
            ]
            figure = charts.scatter_groups(
                groups,
                threshold_x=seuil_att,
                threshold_y=seuil_snr,
                label_x="Downstream attenuation",
                label_y="Noise margin",
                unit_x=" dB",
                unit_y=" dB",
                risk_zone="Degraded line",
            )
            charts.show(figure, height=380, key="qual_nuage")
            shell.caption(
                f"{fmt_int(data.get('nb_points_traces', 0))} points plotted — "
                f"one measurement in {data.get('pas_echantillon', 1)}, "
                f"deterministic sampling. The counts on the right cover the whole "
                f"set of {fmt_int(total)} crossed measurements."
            )

        with detail:
            breakdown = [
                ("Compliant line", quadrants.get("conforme", 0),
                 "Below the attenuation threshold, above the SNR threshold", "good"),
                ("Attenuation only", quadrants.get("attenuation_seule", 0),
                 "Long or degraded cable, noise under control", "warning"),
                ("SNR margin only", quadrants.get("snr_seul", 0),
                 "Noisy line without excessive attenuation", "warning"),
                ("Degraded line", quadrants.get("degradee", 0),
                 "Both thresholds crossed — physical re-intervention", "critical"),
            ]
            cards.feed([
                cards.FeedItem(
                    title=label,
                    message=f"{explanation}.",
                    timestamp=f"{fmt_int(count)} measurements · {fmt_pct(ratio(count, total), 1)}",
                    tone=tone,
                    tag=fmt_pct(ratio(count, total), 1),
                )
                for label, count, explanation, tone in breakdown
            ])

        table = points.copy()
        table["debit_mbps"] = (table["debit_kbps"] / KBPS_PER_MBPS).round(1)
        charts.table_twin(
            table[["technologie", "attenuation", "snr", "debit_mbps", "statut"]].rename(columns={
                "technologie": "Technology", "attenuation": "Attenuation (dB)",
                "snr": "SNR margin (dB)", "debit_mbps": "Rate (Mb/s)", "statut": "Line status",
            }),
            label="View the plotted points",
        )
