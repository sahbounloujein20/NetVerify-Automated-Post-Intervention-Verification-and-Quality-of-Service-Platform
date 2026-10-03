"""
Plotly chart builders.

Rules applied everywhere (they are not negotiable from one chart to the next —
that is what makes the visual unity):

* thin strokes — bars <= 24 px, lines 2 px, markers >= 8 px ringed with the
  surface colour;
* a solid hairline grid on the value axis only, never dotted;
* a legend as soon as there are two series, direct labels used sparingly (end of
  a curve, tip of a bar) — never a number on every point;
* the text carries the ink tokens, never the series colour;
* no dual Y axis.
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import theme
from ..utils import esc

# Plotly toolbar hidden: it adds nothing when reading a dashboard.
CONFIG_STATIC = {"displayModeBar": False, "responsive": True, "doubleClick": False}
CONFIG_MAP = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "toImage"],
}

BAR_MAX_THICKNESS = 24


def show(fig: go.Figure, height: int = 300, key: str | None = None, config: dict | None = None) -> None:
    """Renders a figure with the in-house theme (theme=None: Plotly keeps OUR template)."""
    fig.update_layout(height=height)
    st.plotly_chart(fig, theme=None, width="stretch", key=key, config=config or CONFIG_STATIC)


def _hover(fig: go.Figure, unified: bool = False) -> go.Figure:
    fig.update_layout(hovermode="x unified" if unified else "closest")
    return fig


def table_twin(frame: pd.DataFrame, label: str = "View the chart data") -> None:
    """Tabular twin: every value of a chart stays readable without colour."""
    if frame is None or frame.empty:
        return
    with st.expander(label, icon=":material/table_rows:"):
        st.dataframe(frame, width="stretch", hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# Time series
# ══════════════════════════════════════════════════════════════════════════════

def stacked_columns(
    x: Sequence,
    series: Sequence[tuple[str, Sequence[float], str]],
    total_label: bool = True,
) -> go.Figure:
    """Composition over time. `series` = (label, values, colour).

    The stack carries the composition; the total height carries the volume — no
    extra "Total" curve, which would replay the same information.
    """
    fig = go.Figure()
    for label, values, color in series:
        fig.add_trace(
            go.Bar(
                name=label,
                x=list(x),
                y=list(values),
                marker=dict(
                    color=color,
                    cornerradius=4,
                    # 2 px hairline in the surface colour: it is the gap that
                    # separates the segments, not a contrast outline.
                    line=dict(color=theme.SURFACE, width=2),
                ),
                hovertemplate=f"<b>{label}</b> : %{{y}}<extra></extra>",
            )
        )

    fig.update_layout(barmode="stack", bargap=0.5, legend=dict(traceorder="normal"))

    # With two or three months of history, letting the columns take the whole
    # width would give enormous blocks: a minimum number of slots is reserved so
    # the thickness stays constant whatever the volume of history.
    slots_minimum = 8
    if 0 < len(x) < slots_minimum:
        fig.update_xaxes(range=[-0.5, slots_minimum - 0.5])

    if total_label and len(x):
        totals = [sum(values[i] for _, values, _ in series) for i in range(len(x))]
        fig.add_annotation(
            x=list(x)[-1],
            y=totals[-1],
            text=f"<b>{totals[-1]:,}</b>".replace(",", " "),
            showarrow=False,
            yshift=14,
            font=dict(color=theme.INK, size=12.5),
        )
        fig.update_yaxes(range=[0, max(totals) * 1.18 if max(totals) else 1])

    return _hover(fig, unified=True)


def stacked_area(
    x: Sequence,
    series: Sequence[tuple[str, Sequence[float], str]],
    total_label: bool = True,
) -> go.Figure:
    """Stacked areas with markers — the shape of the original home chart.

    v1 superimposed a "Total" curve over the curves of its own components: the
    same information was plotted twice and the total crushed the scale. Here the
    stack carries the composition, its height carries the total.
    """
    fig = go.Figure()
    for label, values, color in series:
        fig.add_trace(
            go.Scatter(
                name=label,
                x=list(x),
                y=list(values),
                mode="lines+markers",
                stackgroup="one",
                line=dict(color=color, width=2, shape="spline", smoothing=0.5),
                fillcolor=_rgba(color, 0.28),
                marker=dict(size=8, color=color, line=dict(color=theme.SURFACE, width=2)),
                hovertemplate=f"<b>{label}</b> : %{{y}}<extra></extra>",
            )
        )

    if total_label and len(x):
        totals = [sum(values[i] for _, values, _ in series) for i in range(len(x))]
        fig.add_annotation(
            x=list(x)[-1],
            y=totals[-1],
            text=f"<b>{totals[-1]:,}</b>".replace(",", " "),
            showarrow=False,
            yshift=16,
            xshift=-6,
            font=dict(color=theme.INK, size=13),
        )
        fig.update_yaxes(range=[0, max(totals) * 1.2 if max(totals) else 1])

    return _hover(fig, unified=True)


def lines(
    x: Sequence,
    series: Sequence[tuple[str, Sequence[float], str]],
    suffix: str = "",
) -> go.Figure:
    """2 px curves with a ringed end point and a direct label on the right."""
    fig = go.Figure()
    for label, values, color in series:
        fig.add_trace(
            go.Scatter(
                name=label,
                x=list(x),
                y=list(values),
                mode="lines",
                line=dict(color=color, width=2, shape="spline", smoothing=0.4),
                hovertemplate=f"<b>{label}</b> : %{{y}}{suffix}<extra></extra>",
            )
        )
        if len(values):
            fig.add_trace(
                go.Scatter(
                    x=[list(x)[-1]],
                    y=[list(values)[-1]],
                    mode="markers",
                    marker=dict(size=9, color=color, line=dict(color=theme.SURFACE, width=2)),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
    return _hover(fig, unified=True)


def area(x: Sequence, values: Sequence[float], label: str, color: str | None = None) -> go.Figure:
    """Single series: a 10% wash under a 2 px stroke, no legend."""
    color = color or theme.SERIES[0]
    fill = _rgba(color, 0.10)
    x, values = list(x), list(values)
    fig = go.Figure(
        go.Scatter(
            x=x,
            y=values,
            mode="lines",
            line=dict(color=color, width=2, shape="spline", smoothing=0.4),
            fill="tozeroy",
            fillcolor=fill,
            name=label,
            hovertemplate=f"<b>{label}</b> : %{{y}}<extra></extra>",
        )
    )
    # A stroke needs two points to exist: on a single day, the trace above draws
    # strictly nothing (no segment, and no area to fill). The ringed end point —
    # the same one that closes the curves of `lines()` — is what keeps that case
    # readable, and it marks the last value on a full series.
    if x:
        fig.add_trace(
            go.Scatter(
                x=[x[-1]],
                y=[values[-1]],
                mode="markers",
                marker=dict(size=9, color=color, line=dict(color=theme.SURFACE, width=2)),
                cliponaxis=False,
                hoverinfo="skip",
                showlegend=False,
            )
        )
        # Plotly's autorange stops dead on the maximum: the end point would sit
        # astride the top of the frame, half of it cut off.
        top = max(values)
        fig.update_yaxes(range=[0, top * 1.18 if top else 1])
    fig.update_layout(showlegend=False)
    return _hover(fig, unified=True)


# ══════════════════════════════════════════════════════════════════════════════
# Bars
# ══════════════════════════════════════════════════════════════════════════════

def columns(
    labels: Sequence[str],
    values: Sequence[float],
    color: str | None = None,
    value_suffix: str = "",
    min_slots: int | None = None,
) -> go.Figure:
    """Single nominal series: one hue, value placed on top of the bar.

    `min_slots` reserves a number of positions on the axis, as
    `stacked_columns` does: without it, two or three categories are blown up
    into blocks the width of the card.
    """
    color = color or theme.SERIES[0]
    text = [f"{v:,.0f}{value_suffix}".replace(",", " ") for v in values]
    fig = go.Figure(
        go.Bar(
            x=list(labels),
            y=list(values),
            marker=dict(color=color, cornerradius=4),
            text=text,
            textposition="outside",
            textfont=dict(color=theme.INK_2, size=12),
            cliponaxis=False,
            hovertemplate="%{x} : %{y}<extra></extra>",
        )
    )
    top = max(values) if len(values) else 0
    fig.update_layout(showlegend=False, bargap=0.5)
    fig.update_yaxes(range=[0, top * 1.22 if top else 1])
    if min_slots and 0 < len(labels) < min_slots:
        fig.update_xaxes(range=[-0.5, min_slots - 0.5])
    return fig


def grouped_columns(
    labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float], str]],
    value_format: str = "{:,.0f}",
) -> go.Figure:
    """Two comparable series on a single scale (never two Y axes)."""
    fig = go.Figure()
    for name, values, color in series:
        fig.add_trace(
            go.Bar(
                name=name,
                x=list(labels),
                y=list(values),
                marker=dict(color=color, cornerradius=4),
                hovertemplate=f"<b>{name}</b> : %{{y:,.0f}}<extra></extra>",
            )
        )
    fig.update_layout(barmode="group", bargap=0.42, bargroupgap=0.12)
    return fig


def ranked_bars(
    labels: Sequence[str],
    values: Sequence[float],
    color: str | None = None,
    value_suffix: str = "",
    target: float | None = None,
    target_label: str = "Target",
    axis_max: float | None = None,
) -> go.Figure:
    """Horizontal ranking: value at the tip of the bar, target as a vertical hairline."""
    color = color or theme.SERIES[0]
    text = [f"{v:,.0f}{value_suffix}".replace(",", " ") for v in values]
    fig = go.Figure(
        go.Bar(
            x=list(values),
            y=list(labels),
            orientation="h",
            marker=dict(color=color, cornerradius=4),
            text=text,
            textposition="outside",
            textfont=dict(color=theme.INK_2, size=12),
            cliponaxis=False,
            hovertemplate="%{y} : %{x}" + esc(value_suffix) + "<extra></extra>",
        )
    )
    top = axis_max if axis_max is not None else (max(values) * 1.18 if len(values) else 1)
    fig.update_layout(showlegend=False, bargap=0.45)
    fig.update_xaxes(range=[0, top], showgrid=True)
    fig.update_yaxes(showgrid=False, ticksuffix="  ")

    if target is not None:
        fig.add_vline(
            x=target,
            line=dict(color=theme.INK_3, width=1),
            annotation_text=f"{target_label} {target:g}{value_suffix}",
            annotation_position="top",
            annotation_font=dict(color=theme.INK_3, size=11),
        )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Part-to-whole
# ══════════════════════════════════════════════════════════════════════════════

def donut(
    labels: Sequence[str],
    values: Sequence[float],
    colors: Sequence[str],
    center_value: str = "",
    center_label: str = "",
) -> go.Figure:
    """Low-cardinality breakdown (<= 6 slices), total in the centre."""
    fig = go.Figure(
        go.Pie(
            labels=list(labels),
            values=list(values),
            hole=0.68,
            sort=False,
            direction="clockwise",
            marker=dict(colors=list(colors), line=dict(color=theme.SURFACE, width=2)),
            textinfo="none",
            hovertemplate="<b>%{label}</b> : %{value} (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(showlegend=False, margin=dict(l=4, r=4, t=4, b=4))
    if center_value:
        fig.add_annotation(
            text=f"<b>{center_value}</b>", showarrow=False, x=0.5, y=0.54,
            font=dict(size=26, color=theme.INK),
        )
    if center_label:
        fig.add_annotation(
            text=center_label, showarrow=False, x=0.5, y=0.40,
            font=dict(size=11.5, color=theme.INK_3),
        )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Distributions & statistics
# ══════════════════════════════════════════════════════════════════════════════

def histogram(
    centres: Sequence[float],
    effectifs: Sequence[float],
    parts: Sequence[float] | None = None,
    threshold: float | None = None,
    direction: str = "minimum",
    threshold_label: str = "Threshold",
    unit: str = "",
    width: float | None = None,
) -> go.Figure:
    """Histogram of a continuous quantity.

    Two deliberate departures from the nominal bars in this file: the columns
    almost touch (`bargap` 0.06 instead of 0.5), because a histogram represents
    a continuous axis and not separate categories; and no value is placed on the
    tops — there are up to 25 columns, annotating them all would make a wall of
    numbers. The twin table carries the detail.

    `sens` says on which side of the threshold the risk lies (`minimum`: below
    the threshold; `maximum`: above). The affected columns switch to a status
    hue — a state, never a series identity — and the threshold stays doubled by
    a labelled hairline, so colour does not carry the information alone.
    """
    base = theme.SERIES[0]
    alert = theme.STATUS["critical"]

    if threshold is None:
        colours = base
    else:
        colours = [
            alert if ((direction == "minimum" and c < threshold) or (direction == "maximum" and c > threshold))
            else base
            for c in centres
        ]

    parts = list(parts) if parts is not None else [None] * len(list(centres))
    fig = go.Figure(
        go.Bar(
            x=list(centres),
            y=list(effectifs),
            width=width,
            marker=dict(color=colours, cornerradius=3,
                        line=dict(color=theme.SURFACE, width=1)),
            customdata=parts,
            hovertemplate=(
                "%{x}" + esc(unit) + " · %{y} measurements"
                + ("<br>%{customdata} % of the population" if parts[0] is not None else "")
                + "<extra></extra>"
            ),
        )
    )
    fig.update_layout(showlegend=False, bargap=0.06)
    fig.update_xaxes(ticksuffix=unit, showgrid=False)

    if threshold is not None:
        fig.add_vline(
            x=threshold,
            line=dict(color=theme.INK_3, width=1),
            annotation_text=f"{threshold_label} {threshold:g}{unit}",
            annotation_position="top",
            annotation_font=dict(color=theme.INK_3, size=11),
        )
    return fig


def range_bars(
    labels: Sequence[str],
    bottom: Sequence[float],
    middle: Sequence[float],
    top: Sequence[float],
    unit: str = "",
    range_label: str = "P10 – P90 range",
    mid_label: str = "Median",
    color: str | None = None,
) -> go.Figure:
    """Floating P10 -> P90 bars with a median marker ("dumbbell").

    A single average per category would hide the dispersion, which is the useful
    information here: two technologies can share the same median and have
    completely different low tails. The bar carries the span, the diamond the
    central position.
    """
    color = color or theme.SERIES[0]
    etendues = [h - b for b, h in zip(bottom, top)]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name=range_label,
            x=etendues,
            y=list(labels),
            base=list(bottom),
            orientation="h",
            marker=dict(color=_rgba(color, 0.32), cornerradius=4,
                        line=dict(color=color, width=1)),
            customdata=list(zip(bottom, top)),
            hovertemplate=(
                "<b>%{y}</b><br>P10 : %{customdata[0]}" + esc(unit)
                + "<br>P90 : %{customdata[1]}" + esc(unit) + "<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            name=mid_label,
            x=list(middle),
            y=list(labels),
            mode="markers+text",
            marker=dict(symbol="diamond", size=11, color=color,
                        line=dict(color=theme.SURFACE, width=2)),
            text=[f"{v:,.1f}".replace(",", " ").replace(".", ",") for v in middle],
            textposition="top center",
            textfont=dict(color=theme.INK_2, size=11.5),
            hovertemplate="<b>%{y}</b><br>Median: %{x}" + esc(unit) + "<extra></extra>",
        )
    )
    fig.update_layout(bargap=0.55)
    fig.update_xaxes(ticksuffix=unit, showgrid=True)
    fig.update_yaxes(showgrid=False, ticksuffix="  ")
    return fig


def _span(values: Sequence[float], threshold: float | None = None, margin: float = 0.05) -> list[float] | None:
    """Bounds of a series, padded, threshold included — None if nothing to plot."""
    points = [float(v) for v in values if v == v]  # v == v excludes the NaNs
    if threshold is not None:
        points.append(float(threshold))
    if not points:
        return None
    low, high = min(points), max(points)
    padding = (high - low) * margin or 1.0
    return [low - padding, high + padding]


def scatter_groups(
    groups: Sequence[tuple[str, Sequence[float], Sequence[float], str]],
    threshold_x: float | None = None,
    threshold_y: float | None = None,
    label_x: str = "",
    label_y: str = "",
    unit_x: str = "",
    unit_y: str = "",
    risk_zone: str = "",
) -> go.Figure:
    """Scatter plot per group, with thresholds and a shaded risk quadrant.

    The markers are semi-opaque and ringed with the surface colour: over a
    thousand points, solid discs would merge into a blob and the density would
    no longer be readable.
    """
    fig = go.Figure()

    # Plotly folds the shapes into the autorange: a rectangle drawn to +/-1e9
    # stretched both axes to a billion dB and crushed every point onto the
    # origin. The quadrant is therefore clamped to the plotted data and the
    # ranges are set by hand.
    span_x = _span([v for _, xs, _, _ in groups for v in xs], threshold_x)
    span_y = _span([v for _, _, ys, _ in groups for v in ys], threshold_y)

    # The risk rectangle is drawn before the points so it stays underneath.
    if risk_zone and threshold_x is not None and threshold_y is not None and span_x and span_y:
        fig.add_shape(
            type="rect", xref="x", yref="y",
            x0=threshold_x, x1=span_x[1], y0=span_y[0], y1=threshold_y,
            fillcolor=_rgba(theme.STATUS["critical"], 0.10),
            line=dict(width=0), layer="below",
        )

    for label, xs, ys, colour in groups:
        fig.add_trace(
            go.Scatter(
                name=label,
                x=list(xs),
                y=list(ys),
                mode="markers",
                marker=dict(size=7, color=colour, opacity=0.62,
                            line=dict(color=theme.SURFACE, width=1)),
                hovertemplate=(
                    f"<b>{esc(label)}</b><br>{esc(label_x)} : %{{x}}{esc(unit_x)}"
                    f"<br>{esc(label_y)} : %{{y}}{esc(unit_y)}<extra></extra>"
                ),
            )
        )

    filet = dict(color=theme.INK_3, width=1)
    if threshold_x is not None:
        fig.add_vline(x=threshold_x, line=filet)
    if threshold_y is not None:
        fig.add_hline(y=threshold_y, line=filet)

    fig.update_xaxes(title=label_x, ticksuffix=unit_x, showgrid=True, range=span_x)
    fig.update_yaxes(title=label_y, ticksuffix=unit_y, range=span_y)
    return fig


def pareto(
    labels: Sequence[str],
    parts: Sequence[float],
    cumuls: Sequence[float],
    threshold: float = 80.0,
) -> go.Figure:
    """Pareto diagram — share of each cause and curve of the cumulative shares.

    Both series are expressed as percentages, so they share a single 0-100
    scale: that is what makes it possible to do without the second Y axis
    usually seen on this diagram, and which the rest of the dashboard forbids.
    """
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Share of the cause",
            x=list(labels),
            y=list(parts),
            marker=dict(color=theme.SERIES[0], cornerradius=4),
            hovertemplate="<b>%{x}</b><br>%{y} % of the anomalies<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Cumulative",
            x=list(labels),
            y=list(cumuls),
            mode="lines+markers",
            line=dict(color=theme.SERIES[1], width=2),
            marker=dict(size=8, color=theme.SERIES[1],
                        line=dict(color=theme.SURFACE, width=2)),
            hovertemplate="<b>%{x}</b><br>Cumulative: %{y} %<extra></extra>",
        )
    )

    if len(labels):
        fig.add_annotation(
            x=list(labels)[-1], y=list(cumuls)[-1],
            text=f"<b>{list(cumuls)[-1]:.0f} %</b>".replace(".", ","),
            showarrow=False, yshift=15, xshift=-10,
            font=dict(color=theme.INK, size=12.5),
        )

    fig.add_hline(
        y=threshold,
        line=dict(color=theme.INK_3, width=1),
        annotation_text=f"{threshold:g} %",
        annotation_position="right",
        annotation_font=dict(color=theme.INK_3, size=11),
    )
    fig.update_layout(bargap=0.5)
    fig.update_yaxes(range=[0, 108], ticksuffix=" %")
    return fig


def heatmap(
    x_labels: Sequence[str],
    y_labels: Sequence[str],
    values_seq: Sequence[Sequence[float]],
    texts: Sequence[Sequence[str]] | None = None,
    unit: str = "",
    scale_title: str = "",
) -> go.Figure:
    """Heat matrix — single-hue sequential ramp.

    There is no grey for empty cells here: `xgap`/`ygap` let the surface show
    between the cells, exactly like the 2 px hairline that separates the
    segments of the stacked bars elsewhere in this file.
    """
    fig = go.Figure(
        go.Heatmap(
            z=[list(row) for row in values_seq],
            x=list(x_labels),
            y=list(y_labels),
            colorscale=[[i / (len(theme.SEQUENTIAL) - 1), c]
                        for i, c in enumerate(theme.SEQUENTIAL)],
            xgap=2,
            ygap=2,
            text=[list(row) for row in texts] if texts is not None else None,
            texttemplate="%{text}" if texts is not None else None,
            textfont=dict(color=theme.INK, size=12),
            hovertemplate="<b>%{y} · %{x}</b><br>%{z}" + esc(unit) + "<extra></extra>",
            colorbar=dict(
                title=dict(text=scale_title, font=dict(color=theme.INK_3, size=11)),
                tickfont=dict(color=theme.INK_3, size=11),
                outlinewidth=0,
                thickness=10,
                len=0.85,
                ticksuffix=unit,
            ),
        )
    )
    fig.update_xaxes(showgrid=False, side="top")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

def _rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i: i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"
