"""Cartography — geographic distribution of the work orders across Greater Tunis.

Map built on `go.Scattermap` (MapLibre engine) rather than on `Scattergeo`:

* `Scattergeo` has no tiles — the points floated on a black background with no
  geographic context — and preserves the aspect ratio of its projection, which
  left two empty bands to the left and right of the container;
* `Scattermap` takes the whole width, shows a real dark base map (Carto Dark
  Matter, no token) and can group the points (`cluster`, which relies on
  supercluster in the browser);
* the zone names are no longer painted permanently: 33 labels over a few square
  kilometres overlapped. They move into the tooltip, and stay switchable on
  demand once zoomed in.
"""

from __future__ import annotations

import math

import plotly.graph_objects as go
import streamlit as st

from .. import api, theme
from ..settings import COMPLIANT_THRESHOLD, WATCH_THRESHOLD, TECHNOLOGIES
from ..utils import fmt_int, fmt_pct, to_frame
from ..ui import cards, charts, shell, states, tables
from ..ui.cards import Tile

# Resolution tiers.
#
# On a tile background, the marker shape is not a reliable channel: the symbols
# of `Scattermap` depend on the style's sprite and an unknown name makes the
# point invisible. The hue therefore no longer carries the meaning alone — green
# and red merge under deuteranopia (ΔE 5.6) — it is doubled by the legend label,
# the tier written in the tooltip and the "Tier" column of the table.
TIERS = [
    ("Compliant", "good", f"≥ {COMPLIANT_THRESHOLD:g} %"),
    ("To watch", "warning", f"{WATCH_THRESHOLD:g} – {COMPLIANT_THRESHOLD:g} %"),
    ("Critical", "critical", f"< {WATCH_THRESHOLD:g} %"),
]
TIER_LABEL = {key: label for label, key, _ in TIERS}

BASE_MAPS = {
    "Dark": "carto-darkmatter",
    "Dark, no labels": "carto-darkmatter-nolabels",
    "Detailed street map": "open-street-map",
}

NUMERIC_COLUMNS = ("total", "traitees", "en_cours", "emises", "taux_resolution", "lat", "lon")


def render() -> None:
    shell.render_page_header(
        "Cartography",
        "Location of the work orders per intervention zone: the volume sizes "
        "the point, the resolution rate fixes its tier.",
        "map-pin",
    )

    result = api.get("/stats/work-orders-by-place")
    if result.failed:
        states.offline_banner()
        with shell.card("geo-error"):
            states.error_state(result, "the geographic data")
        return
    if result.empty:
        with shell.card("geo-empty"):
            states.empty_state(
                "No geolocated zone",
                "No work order carries a zone known to the coordinate referential.",
                "map-pin",
            )
        return

    frame = to_frame(result.list(), numeric=NUMERIC_COLUMNS)
    by_zone = _aggregate(frame)

    # The indicators always reason at the zone level, never at the
    # zone x technology pair, otherwise one zone would be counted three times.
    _kpi_row(by_zone)
    shell.spacer(10)

    technology, base_map, labels_on = _filters()
    view = by_zone if technology == "All" else frame[frame["technologie"] == technology]
    if view.empty:
        with shell.card("geo-vide"):
            states.empty_state(
                "No data",
                f"No zone reports a work order on {technology}.",
                "map-pin",
            )
        return

    view = view.copy()
    view["palier"] = view["taux_resolution"].map(theme.status_of)
    view["palier_libelle"] = view["palier"].map(TIER_LABEL)

    _map(view, BASE_MAPS[base_map], labels_on)
    shell.spacer(10)

    left, right = st.columns(2, gap="medium")
    with left:
        _volume_card(view)
    with right:
        _resolution_card(view)

    shell.spacer(10)
    _detail_card(view)


# ══════════════════════════════════════════════════════════════════════════════

def _aggregate(frame):
    """Groups the zone x technology rows into one row per zone.

    The backend splits each zone by technology: without grouping, the map would
    stack three bubbles on the same coordinates.
    """
    group = (
        frame.groupby(["zone", "lat", "lon"], as_index=False)
        .agg({"total": "sum", "traitees": "sum", "en_cours": "sum", "emises": "sum"})
    )
    group["technologie"] = "All technologies"
    group["taux_resolution"] = (
        group["traitees"] / group["total"].replace(0, 1) * 100
    ).round(1)
    return group


def _kpi_row(frame) -> None:
    total = float(frame["total"].sum())
    mean = float(frame["taux_resolution"].mean())
    plus_active = frame.loc[frame["total"].idxmax()]
    critiques = int((frame["taux_resolution"] < WATCH_THRESHOLD).sum())

    cards.tile_row([
        Tile(label="Zones covered", value=fmt_int(frame["zone"].nunique()),
             icon="map-pin", note="Geolocated sites"),
        Tile(label="Localised work orders", value=fmt_int(total),
             icon="inbox", note="All technologies"),
        Tile(label="Average resolution rate", value=fmt_pct(mean, 1).rstrip("%"), unit="%",
             icon="check", tone=theme.status_of(mean), note="Average of the zones",
             meter=(mean, 100)),
        Tile(label="Busiest zone", value=str(plus_active["zone"]),
             icon="alert", tone="warning",
             note=f"{fmt_int(plus_active['total'])} work orders"),
        Tile(label="Critical zones", value=fmt_int(critiques),
             icon="target", tone="critical" if critiques else "good",
             note=f"Resolution < {WATCH_THRESHOLD:g} %"),
    ])


def _filters() -> tuple[str, str, bool]:
    with shell.card("geo-filtres"):
        col1, col2, col3, _ = st.columns([1, 1, 1.2, 1.4], vertical_alignment="bottom")
        with col1:
            technology = st.selectbox("Technology", ["All", *TECHNOLOGIES], key="geo_techno")
        with col2:
            base_map = st.selectbox("Base map", list(BASE_MAPS), key="geo_fond")
        with col3:
            labels_on = st.toggle(
                "Zone names", value=False, key="geo_labels",
                help="Off by default: at this zoom level the 33 names overlap. "
                     "The name stays readable when hovering each point.",
            )
    return technology, base_map, labels_on


def _framing(view, width_px: int = 1200, height_px: int = 560, margin: float = 1.4):
    """Centre and zoom level covering every displayed zone.

    Web Mercator projection: 360° of longitude occupy 256·2^zoom pixels, and the
    vertical scale is divided by cos(latitude).
    """
    lat_min, lat_max = float(view["lat"].min()), float(view["lat"].max())
    lon_min, lon_max = float(view["lon"].min()), float(view["lon"].max())
    centre_lat = (lat_min + lat_max) / 2
    centre = {"lat": centre_lat, "lon": (lon_min + lon_max) / 2}

    span_lon = max((lon_max - lon_min) * margin, 0.004)
    span_lat = max((lat_max - lat_min) * margin, 0.004)

    zoom_lon = math.log2(360 * width_px / (256 * span_lon))
    zoom_lat = math.log2(360 * height_px * math.cos(math.radians(centre_lat)) / (256 * span_lat))
    return centre, max(3.0, min(15.0, min(zoom_lon, zoom_lat)))


def _map(view, style: str, labels_on: bool) -> None:
    with shell.card("geo-carte"):
        shell.section(
            "Map of the intervention zones",
            "Point size = work-order volume · colour = resolution tier. "
            "Nearby points group together; zoom in to separate them.",
            aside=f"{fmt_int(len(view))} zones displayed",
        )
        shell.legend(
            [(theme.STATUS[key], f"{label} ({borne})", "dot") for label, key, borne in TIERS],
            note="Hover a point for the numeric detail",
        )

        maximum = float(view["total"].max()) or 1.0
        centre, zoom = _framing(view)

        figure = go.Figure()
        for label, key, _ in TIERS:
            group = view[view["palier"] == key]
            if group.empty:
                continue
            colour = theme.STATUS[key]
            figure.add_trace(
                go.Scattermap(
                    name=label,
                    lat=group["lat"],
                    lon=group["lon"],
                    mode="markers+text" if labels_on else "markers",
                    text=group["zone"],
                    textposition="top center",
                    textfont=dict(color=theme.INK, size=11),
                    marker=dict(
                        color=colour,
                        opacity=0.88,
                        size=group["total"],
                        sizemode="area",
                        sizeref=2.0 * maximum / (30.0 ** 2),
                        sizemin=6,
                        allowoverlap=True,
                    ),
                    # Native grouping (supercluster): beyond zoom 13 the points
                    # become individual again.
                    cluster=dict(
                        enabled=True,
                        color=colour,
                        opacity=0.92,
                        size=[18, 26, 34],
                        step=[0, 6, 18],
                        maxzoom=13,
                    ),
                    customdata=group[["total", "traitees", "en_cours", "emises",
                                       "taux_resolution", "technologie", "palier_libelle"]].values,
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        "Tier: %{customdata[6]}<br>"
                        "Technology: %{customdata[5]}<br>"
                        "Total: %{customdata[0]}<br>"
                        "Processed: %{customdata[1]}<br>"
                        "In progress: %{customdata[2]}<br>"
                        "Issued: %{customdata[3]}<br>"
                        "Resolution: %{customdata[4]} %<extra></extra>"
                    ),
                )
            )

        figure.update_layout(
            showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            # The in-house template pins `dragmode` to False; on a map that would
            # forbid any panning.
            dragmode="pan",
            map=dict(style=style, center=centre, zoom=zoom),
        )
        charts.show(figure, height=560, key="geo_map", config=charts.CONFIG_MAP)

        st.html(
            '<div class="legend-note" style="margin-top:10px">Base map '
            "© OpenStreetMap · © CARTO — the tiles require a connection; "
            "offline, the points stay displayed on a plain background.</div>"
        )


def _volume_card(view) -> None:
    with shell.card("geo-volume", height="stretch"):
        shell.section("Busiest zones", "Top 10 by work-order volume.")
        ranking = view.sort_values("total", ascending=True).tail(10)
        figure = charts.ranked_bars(ranking["zone"], ranking["total"])
        charts.show(figure, height=306, key="geo_volume")
        charts.table_twin(
            ranking.sort_values("total", ascending=False)[["zone", "total"]]
            .rename(columns={"zone": "Zone", "total": "Work orders"})
        )


def _resolution_card(view) -> None:
    with shell.card("geo-resolution", height="stretch"):
        shell.section(
            "Zones lagging the most",
            f"Lowest resolution rate. Critical tier below {WATCH_THRESHOLD:g} %.",
        )
        ranking = view.sort_values("taux_resolution", ascending=False).tail(10)
        figure = charts.ranked_bars(
            ranking["zone"], ranking["taux_resolution"],
            value_suffix=" %", target=COMPLIANT_THRESHOLD, target_label="Compliant tier",
            axis_max=118,
        )
        charts.show(figure, height=306, key="geo_resolution")
        charts.table_twin(
            ranking[["zone", "taux_resolution"]]
            .rename(columns={"zone": "Zone", "taux_resolution": "Resolution (%)"})
        )


def _detail_card(view) -> None:
    with shell.card("geo-detail"):
        shell.section("Detail per zone", "Every value carried by the map, spelled out.")
        columns = ["zone", "palier_libelle", "technologie", "total",
                    "traitees", "en_cours", "emises", "taux_resolution"]
        tables.data_table(
            view.sort_values("total", ascending=False),
            key="geo_table",
            height=380,
            columns=columns,
            config={
                "zone": tables.text_col("zone", "large"),
                # The tier spelled out: the map colour is never the only way to
                # know the state of a zone.
                "palier_libelle": st.column_config.TextColumn("Tier", width="small"),
                "technologie": tables.text_col("technologie", "small"),
                "total": tables.number_col("total"),
                "traitees": tables.number_col("traitees"),
                "en_cours": tables.number_col("en_cours"),
                "emises": tables.number_col("emises"),
                "taux_resolution": tables.percent_col("taux_resolution"),
            },
        )
        tables.export_button(view, "netverify_zones.csv", "geo_export")
