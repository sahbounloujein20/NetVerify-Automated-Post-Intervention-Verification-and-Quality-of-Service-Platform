"""My results — what a technician sees in place of the nominative rankings.

The Analytics page ranks the field agents by name: it belongs to whoever is
responsible for them, not to their peers. Closing it without giving anything
back would simply leave a technician blind, so this page is the counterpart. It
answers the three questions the agent actually has about their own work:

1. **Where do I stand?** My compliance rate, against the team median.
2. **What is attributed to me?** My anomaly count, against the team median.
3. **What do I do about it?** The list of my work orders to go back to.

The team appears only as an anonymous benchmark — median, headcount, how many
peers score below me. No colleague is ever named, which is precisely what
separates a self-view from a ranking.
"""

from __future__ import annotations

import streamlit as st

from .. import api, auth, theme
from ..settings import COMPLIANCE_TARGET
from ..utils import esc, fmt_datetime, fmt_int, fmt_pct, ratio, to_frame
from ..ui import cards, charts, shell, states, tables
from ..ui.cards import FeedItem, Tile


def render() -> None:
    shell.render_page_header(
        "My results",
        "Your own interventions, measured against the internal target and "
        "against an anonymous team benchmark.",
        "check",
    )

    result = api.get("/stats/my-performance")

    if result.failed:
        states.offline_banner()
        with shell.card("mine-error"):
            states.error_state(result, "your results")
        return

    data = result.dict()

    # A supervisor, or an account that no operational record is attached to. Not
    # an error: the account simply owns no intervention of its own.
    if not data.get("linked"):
        _unlinked_card(data)
        return

    _kpi_row(data)
    shell.spacer(10)

    left, right = st.columns([1, 1.1], gap="medium")
    with left:
        _benchmark_card(data)
    with right:
        _standing_card(data)

    shell.spacer(10)
    _my_anomalies_card()


# ══════════════════════════════════════════════════════════════════════════════

def _unlinked_card(data: dict) -> None:
    with shell.card("mine-unlinked"):
        if auth.is_supervisor():
            states.empty_state(
                "No personal results",
                "Your account supervises the estate rather than carrying "
                "interventions. The nominative figures of the whole team are on "
                "the Analytics page.",
                "users",
            )
            return

        states.empty_state(
            "Account not linked to a technician record",
            "Your sign-in exists but is attached to no identifier in the "
            "technician referential, so no intervention can be matched to it. "
            "Ask the NetVerify administrator to link it.",
            "alert",
        )


def _kpi_row(data: dict) -> None:
    rate = float(data.get("compliance_rate", 0))
    median = float(data.get("team_median_compliance", 0))
    anomalies = int(data.get("anomalies", 0))
    median_anomalies = float(data.get("team_median_anomalies", 0))
    total = int(data.get("total", 0))
    closed = int(data.get("closed", 0))

    cards.tile_row([
        Tile(
            label="My compliance",
            value=fmt_pct(rate, 1).rstrip("%"),
            unit="%",
            icon="check",
            tone=theme.status_of(rate),
            note=f"Target {COMPLIANCE_TARGET:g} %",
            meter=(rate, COMPLIANCE_TARGET),
        ),
        Tile(
            label="Team median",
            value=fmt_pct(median, 1).rstrip("%"),
            unit="%",
            icon="users",
            tone="neutral",
            note=f"Across {fmt_int(data.get('team_size', 0))} technicians",
        ),
        Tile(
            label="My interventions",
            value=fmt_int(total),
            icon="inbox",
            note=f"{fmt_int(closed)} closed ({fmt_pct(ratio(closed, total))})"
                 if total else "None assigned yet",
        ),
        Tile(
            label="Anomalies attributed to me",
            value=fmt_int(anomalies),
            icon="alert",
            tone="critical" if anomalies > median_anomalies else "good",
            note=f"Team median: {median_anomalies:.1f}".replace(".", ","),
        ),
    ])


def _benchmark_card(data: dict) -> None:
    """My rate, the team median and the target, on one scale.

    Three bars rather than a ranking: the comparison the technician needs is
    with a threshold and with the middle of the team, not with a named
    colleague.
    """
    rate = float(data.get("compliance_rate", 0))
    median = float(data.get("team_median_compliance", 0))

    # Which record the figures are computed from. Without it the page shows a
    # score whose perimeter the technician cannot check — and an account linked
    # to the wrong identifier would look perfectly normal.
    identity = " · ".join(
        part for part in (data.get("technician_name"), data.get("technician_id"))
        if part
    )

    with shell.card("mine-benchmark", height="stretch"):
        shell.section(
            "My compliance against the team",
            f"Share of my interventions closed. Internal target: "
            f"{COMPLIANCE_TARGET:g} %.",
            aside=identity,
        )

        if not data.get("has_activity"):
            states.empty_state(
                "No intervention yet",
                "No work order is assigned to your identifier, so no rate can "
                "be computed. The team median is shown in the tiles above.",
                "inbox",
            )
            return

        shell.legend([
            (theme.SERIES[0], "Me", "bar"),
            (theme.INK_3, "Team median", "bar"),
        ], note=f"Target line at {COMPLIANCE_TARGET:g} %")

        figure = charts.ranked_bars(
            ["Team median", "Me"],
            [median, rate],
            value_suffix=" %",
            target=COMPLIANCE_TARGET,
            axis_max=118,
        )
        # Two bars of different meaning: mine takes the series colour, the
        # benchmark stays neutral so it reads as a reference and not as a rival.
        figure.update_traces(marker_color=[theme.INK_3, theme.SERIES[0]])
        charts.show(figure, height=250, key="mine_benchmark")


def _standing_card(data: dict) -> None:
    """Position within the team, expressed without naming anyone."""
    team = int(data.get("team_size", 0))
    below = int(data.get("peers_below", 0))
    rate = float(data.get("compliance_rate", 0))
    percentile = ratio(below, team) if team else 0.0

    with shell.card("mine-standing", height="stretch"):
        shell.section(
            "My position",
            "Where my rate falls among the technicians of the referential.",
        )

        if not data.get("has_activity"):
            states.empty_state(
                "Position not computable",
                "A position requires at least one intervention.",
                "target",
            )
            return

        verdict = (
            "above the internal target" if rate >= COMPLIANCE_TARGET
            else "below the internal target"
        )
        shell.key_values([
            ("My rate", fmt_pct(rate)),
            ("Team median", fmt_pct(float(data.get("team_median_compliance", 0)))),
            ("Technicians I am ahead of", f"{fmt_int(below)} of {fmt_int(team)}"),
            ("Percentile", fmt_pct(percentile, 0)),
            ("Verdict", verdict.capitalize()),
        ])

        st.html(
            f"""
            <div class="legend-note" style="margin-top:16px">
              Read as: your closure rate is higher than that of
              {esc(fmt_int(below))} of the {esc(fmt_int(team))} technicians in
              the referential. Their names are not shown here — only a
              supervisor sees the nominative ranking.
            </div>
            """
        )


def _my_anomalies_card() -> None:
    """The actionable half: my own work orders to go back to."""
    result = api.get("/stats/my-anomalies", limit=50)

    with shell.card("mine-anomalies"):
        shell.section(
            "My work orders to review",
            "Gaps journalled by the D+14 control on interventions attributed "
            "to me, most recent first.",
        )

        if not states.guard(
            result, "your anomalies",
            title="No gap attributed to you",
            message="The D+14 control has journalled nothing on your "
                    "interventions. Nothing to review.",
            icon_name="shield",
        ):
            return

        frame = to_frame(result.list())

        feed, table = st.columns([1, 1.35], gap="medium")

        with feed:
            cards.feed([
                FeedItem(
                    title=entry.get("ref_demande") or "—",
                    message=entry.get("message_log") or "—",
                    timestamp=fmt_datetime(entry.get("date_test")),
                    tone="critical" if entry.get("statut_test") == "ANOMALIE" else "good",
                    tag="Anomaly" if entry.get("statut_test") == "ANOMALIE" else "Compliant",
                )
                for entry in frame.head(4).to_dict("records")
            ])

        with table:
            columns = [c for c in ("ref_demande", "num_appel", "statut_test",
                                   "message_log", "date_test")
                       if c in frame.columns]
            tables.data_table(
                frame,
                key="mine_anomalies_table",
                height=300,
                columns=columns,
                config={
                    "ref_demande": tables.text_col("ref_demande", "medium"),
                    "num_appel": tables.text_col("num_appel", "small"),
                    "statut_test": tables.text_col("statut_test", "small"),
                    "message_log": tables.text_col("message_log", "large"),
                    "date_test": tables.datetime_col("date_test"),
                },
            )
            tables.export_button(frame, "netverify_mes_anomalies.csv", "mine_export")
