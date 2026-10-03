"""
ARCHIVE — version 1 of the NetVerify dashboard (single file, Streamlit tabs).

Kept as it is: the project is not under version control and this version
serves as the "before / after" comparison point for the internship report.
It is no longer executed by the application; the entry point is
`frontend/dashboard.py`.

Running this archive, if needed:
    python -m streamlit run _legacy/dashboard_v1.py
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components

API_URL = "http://127.0.0.1:8000"
APP_DIR = Path(__file__).parent
CHATBOT_PATH = APP_DIR.parent / "chatbot.html"  # archived: the widget stayed at the root

st.set_page_config(
    page_title="NetVerify - Dashboard",
    page_icon="NV",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
:root {
    --bg: #0a0e14;
    --panel: #10161c;
    --panel-2: #141b26;
    --line: rgba(255, 255, 255, 0.08);
    --line-strong: rgba(0, 114, 188, 0.35);
    --text: #eef2f6;
    --muted: #8b9aad;
    --accent: #0072bc;
    --accent-2: #1478c8;
    --green: #1e9e6b;
    --amber: #d97706;
    --red: #dc3545;
}
html, body, [class*="css"] { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
.stApp {
    background:
        radial-gradient(circle at 20% -10%, rgba(0,114,188,0.14), transparent 32%),
        radial-gradient(circle at 80% -6%, rgba(20,120,200,0.08), transparent 30%),
        var(--bg);
    color: var(--text);
}
.block-container { padding: 1.35rem 1.65rem 2.5rem; max-width: 1440px; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }
[data-testid="stSidebar"] { display: none; }

.nav-shell {
    width: min(1040px, 100%);
    margin: 0 auto 1.15rem;
    padding: 10px 18px;
    border: 1px solid var(--line);
    border-radius: 20px;
    background: rgba(10, 14, 20, 0.92);
    box-shadow: 0 20px 55px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04);
    display: flex;
    align-items: center;
    gap: 22px;
}
.brand-mark {
    width: 32px; height: 32px; border-radius: 9px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    box-shadow: 0 2px 10px rgba(0,114,188,0.35);
}
.brand-name { font-weight: 850; letter-spacing: 0; line-height: 1; }
.brand-name span { color: var(--accent-2); }
.brand-sub { color: #6b7686; font-size: 10px; font-weight: 700; letter-spacing: .11em; margin-top: 3px; }
.nav-title { display:flex; align-items:center; gap:12px; min-width: 178px; }
.nav-items { flex: 1; display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; }
.nav-chip {
    color: #7c8798; font-weight: 700; padding: 10px 14px; border-radius: 10px; font-size: 14px;
    border: 1px solid transparent;
    transition: color 0.15s ease, background 0.15s ease;
}
.nav-chip:hover:not(.active) { color: #cfd6de; background: rgba(255,255,255,0.04); }
.nav-chip.active {
    color: #fff; background: linear-gradient(90deg, rgba(0,114,188,0.24), rgba(20,120,200,0.14)); border-color: rgba(0,114,188,0.32);
    box-shadow: inset 0 -2px 0 var(--accent);
}
.status-pill { color: var(--muted); border-left: 1px solid var(--line); padding-left: 16px; font-size: 12px; white-space: nowrap; }
.status-dot { display:inline-block; width:8px; height:8px; border-radius:999px; margin-right:7px; background: var(--green); box-shadow: 0 0 0 3px rgba(30,158,107,0.15); }
.status-dot.off { background: var(--red); box-shadow: 0 0 0 3px rgba(220,53,69,0.15); }

.hero {
    min-height: 220px;
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)), var(--panel);
    border-radius: 12px;
    display: grid;
    place-items: center;
    text-align: center;
    margin: 18px 0 36px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.035);
}
.hero-icon {
    width: 68px; height: 68px; margin: 0 auto 20px; display:grid; place-items:center;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    border-radius: 18px;
    color: #fff; font-weight: 900; font-size: 22px; letter-spacing: 0;
    box-shadow: 0 8px 24px rgba(0,114,188,0.3);
}
.hero h1 { margin: 0; font-size: clamp(26px, 3vw, 38px); font-weight: 800; letter-spacing: 0; }
.hero p { margin: 10px 0 0; color: var(--muted); font-size: 16px; }

.card {
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.028), rgba(255,255,255,0.012)), var(--panel);
    border-radius: 12px;
    padding: 22px 24px;
    min-height: 154px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}
.card:hover {
    transform: translateY(-2px);
    border-color: rgba(0,114,188,0.32);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 12px 28px rgba(0,0,0,0.28);
}
.card-title { display:flex; align-items:center; gap:12px; color: var(--text); font-weight: 750; font-size: 17px; margin-bottom: 24px; }
.card-icon { width:44px; height:44px; display:grid; place-items:center; border-radius: 12px; font-weight: 800; }
.icon-primary   { background: rgba(0,114,188,.15); color: var(--accent-2); }
.icon-secondary { background: rgba(20,120,200,.12); color: #6cb4e8; }
.icon-neutral   { background: rgba(139,154,173,.14); color: var(--muted); }
.kpi-row { display:flex; gap:30px; flex-wrap:wrap; }
.kpi-value { color:#fff; font-size: 28px; font-weight: 800; line-height: 1; }
.kpi-label { color: var(--muted); font-size: 13px; margin-top: 6px; }
.panel-title { color: var(--text); font-size: 18px; font-weight: 750; margin: 0 0 18px; display:flex; align-items:center; gap:10px; }
.panel-title .accent { color: var(--accent-2); }
.panel-title .cyan { color: var(--accent-2); }

section[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.panel-title) {
    border: 1px solid var(--line);
    background: var(--panel);
    border-radius: 12px;
    padding: 24px;
}
.stTabs [data-baseweb="tab-list"] { gap: 8px; justify-content: center; margin-bottom: 18px; }
.stTabs [data-baseweb="tab"] {
    border-radius: 10px; padding: 8px 16px; color: #7c8798; font-weight: 700;
    background: transparent; border: 1px solid transparent;
}
.stTabs [aria-selected="true"] {
    color: #fff; background: linear-gradient(90deg, rgba(0,114,188,.22), rgba(20,120,200,.12)); border-color: rgba(0,114,188,.28);
}
.stButton > button {
    border-radius: 10px; border: 1px solid rgba(0,114,188,0.32); background: linear-gradient(90deg, rgba(0,114,188,0.16), rgba(20,120,200,0.1));
    color: #fff; font-weight: 700; min-height: 40px;
    transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease;
}
.stButton > button:hover { border-color: var(--accent); color: #fff; background: linear-gradient(90deg, var(--accent), var(--accent-2)); transform: translateY(-1px); }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.small-muted { color: var(--muted); font-size: 13px; }

@media (max-width: 860px) {
    .nav-shell { border-radius: 16px; align-items:flex-start; flex-direction: column; }
    .nav-items { justify-content:flex-start; }
    .status-pill { border-left: 0; padding-left: 0; }
    .hero { min-height: 200px; }
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=30, show_spinner=False)
def api(endpoint: str):
    try:
        response = requests.get(f"{API_URL}{endpoint}", timeout=6)
        response.raise_for_status()
        return response.json()
    except Exception:
        return []


def post_api(endpoint: str, payload=None, timeout=30):
    try:
        response = requests.post(f"{API_URL}{endpoint}", json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc)}


def backend_ok() -> bool:
    try:
        return requests.get(f"{API_URL}/", timeout=2).status_code == 200
    except Exception:
        return False


def nf(value):
    try:
        return f"{int(value):,}".replace(",", " ")
    except Exception:
        return str(value or 0)


def plot_layout(height=320):
    return dict(
        height=height,
        margin=dict(l=12, r=18, t=18, b=24),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#eef2f6", size=12),
        xaxis=dict(gridcolor="rgba(255,255,255,0.07)", zeroline=False),
        yaxis=dict(gridcolor="rgba(255,255,255,0.07)", zeroline=False),
    )


def section_title(text, color_class="accent"):
    st.markdown(f'<div class="panel-title"><span class="{color_class}">||</span>{text}</div>', unsafe_allow_html=True)


def kpi_card(title, icon, icon_class, values):
    cells = "".join(
        f'<div><div class="kpi-value">{value}</div><div class="kpi-label">{label}</div></div>'
        for value, label in values
    )
    st.markdown(
        f"""
        <div class="card">
            <div class="card-title"><div class="card-icon {icon_class}">{icon}</div>{title}</div>
            <div class="kpi-row">{cells}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


PAGES = [
    "Dashboard",
    "Clients",
    "Work orders",
    "Analyses",
    "Carte",
    "Logs",
]

if "page" not in st.session_state:
    st.session_state.page = "Dashboard"

status = backend_ok()
nav_html = "".join(
    f'<span class="nav-chip {"active" if page == st.session_state.page else ""}">{page}</span>'
    for page in PAGES
)
st.markdown(
    f"""
    <div class="nav-shell">
        <div class="nav-title">
            <div class="brand-mark"></div>
            <div><div class="brand-name">Net<span>Verify</span></div><div class="brand-sub">TUNISIE TELECOM</div></div>
        </div>
        <div class="nav-items">{nav_html}</div>
        <div class="status-pill"><span class="status-dot {'off' if not status else ''}"></span>{'Backend actif' if status else 'Backend hors ligne'}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

selected = st.tabs(PAGES)
for idx, page in enumerate(PAGES):
    with selected[idx]:
        st.session_state.page = page

kpis = api("/stats/kpis") or {}
work_orders = api("/work-orders?limit=10") or []
logs = api("/logs?limit=8") or []

with selected[0]:
    st.markdown(
        """
        <div class="hero">
            <div>
                <div class="hero-icon">NV</div>
                <h1>Welcome to NetVerify</h1>
                <p>Post-intervention verification and network quality-of-service platform</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    total = kpis.get("total_reclamations", 0)
    processed = kpis.get("total_traitees", 0)
    anomalies = kpis.get("total_anomalies", 0)
    clients = kpis.get("total_clients", 0)
    to_verify = kpis.get("reclamations_a_verifier", 0)
    rate = round((processed / total) * 100, 1) if total else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Overview", "O", "icon-primary", [(nf(total), "Work orders"), (f"{rate}%", "Resolution")])
    with c2:
        kpi_card("Quality follow-up", "Q", "icon-secondary", [(nf(clients), "Customers"), (nf(to_verify), "D+14"), (nf(anomalies), "Anomalies")])
    with c3:
        kpi_card("Recent activity", "A", "icon-neutral", [(nf(len(work_orders)), "Recent"), (nf(len(logs)), "Alerts")])

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([2, 1])

    with left:
        section_title("Compliance overview")
        data = api("/stats/monthly-trend")
        if data:
            df = pd.DataFrame(data)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["mois"], y=df["total"], mode="lines+markers", name="Total", line=dict(color="#0072bc", width=3), fill="tozeroy", fillcolor="rgba(0,114,188,.10)"))
            fig.add_trace(go.Scatter(x=df["mois"], y=df["traitees"], mode="lines+markers", name="Processed", line=dict(color="#1e9e6b", width=2)))
            fig.add_trace(go.Scatter(x=df["mois"], y=df["en_cours"], mode="lines+markers", name="En cours", line=dict(color="#d97706", width=2, dash="dot")))
            fig.update_layout(**plot_layout(315), legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No time-series data available.")

    with right:
        section_title("Latest alerts", "cyan")
        if logs:
            for item in logs[:5]:
                st.markdown(
                    f"""
                    <div style="border-bottom:1px solid rgba(255,255,255,.07);padding:10px 0;">
                        <div style="color:#fff;font-weight:750;">{item.get('ref_demande','N/A')}</div>
                        <div class="small-muted">{item.get('message_log','')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.success("No recent anomaly.")

    st.markdown("<br>", unsafe_allow_html=True)
    g1, g2, g3 = st.columns(3)
    with g1:
        section_title("By technology")
        data_t = api("/stats/anomalies-by-technology")
        if data_t:
            df_t = pd.DataFrame(data_t)
            fig = go.Figure(go.Bar(x=df_t["technologie"], y=df_t["nb_anomalies"], marker_color=["#0072bc", "#1478c8", "#5aa9dc"][: len(df_t)], text=df_t["nb_anomalies"], textposition="outside"))
            fig.update_layout(**plot_layout(260), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with g2:
        section_title("By status")
        data_e = api("/stats/by-status")
        if data_e:
            df_e = pd.DataFrame(data_e)
            colors = {"Traite": "#1e9e6b", "En cours": "#d97706", "Emis": "#0072bc"}
            fig = go.Figure(go.Pie(labels=df_e["etat_ot"], values=df_e["nb"], hole=.64, marker=dict(colors=[colors.get(x, "#8b9aad") for x in df_e["etat_ot"]])))
            fig.update_layout(**plot_layout(260), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
    with g3:
        section_title("Par FSI")
        data_fsi = api("/stats/by-isp")
        if data_fsi:
            df_fsi = pd.DataFrame(data_fsi).sort_values("nb_reclamations", ascending=True).tail(8)
            fig = go.Figure(go.Bar(x=df_fsi["nb_reclamations"], y=df_fsi["fsi"], orientation="h", marker_color="#0072bc", text=df_fsi["nb_reclamations"], textposition="outside"))
            fig.update_layout(**plot_layout(260), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

with selected[1]:
    section_title("Clients")
    f1, f2, f3 = st.columns([1, 1, 4])
    with f1:
        technology = st.selectbox("Technology", ["All", "ADSL", "VDSL", "GPON"])
    with f2:
        limit = st.number_input("Limite", 10, 500, 100, step=10)
    endpoint = f"/clients?limit={limit}" + (f"&technology={technology}" if technology != "All" else "")
    clients_data = api(endpoint)
    if clients_data:
        st.dataframe(pd.DataFrame(clients_data), use_container_width=True, hide_index=True, height=520)
    else:
        st.info("Aucun client disponible ou backend hors ligne.")

with selected[2]:
    section_title("Work orders")
    r1, r2, r3 = st.columns([1, 1, 4])
    with r1:
        status = st.selectbox("Status", ["All", "Emis", "En cours", "Traite"])
    with r2:
        if st.button("Run D+14 verification"):
            result = post_api("/verification/run")
            st.success(result.get("message", "Verification completed.")) if "error" not in result else st.error(result["error"])
            st.cache_data.clear()
    rec_endpoint = "/work-orders?limit=250" + (f"&etat_ot={status}" if status != "All" else "")
    recs = api(rec_endpoint)
    if recs:
        df = pd.DataFrame(recs)
        columns = [c for c in ["ref_demande", "num_appel", "fsi", "debit", "type_demande", "type_ot", "etat_ot", "date_etat"] if c in df.columns]
        st.dataframe(df[columns], use_container_width=True, hide_index=True, height=560)
    else:
        st.info("No work order.")

with selected[3]:
    section_title("Advanced analytics")
    a1, a2 = st.columns(2)
    with a1:
        data = api("/stats/rate-comparison")
        if data:
            df = pd.DataFrame(data)
            fig = go.Figure()
            fig.add_trace(go.Bar(name="Promised rate", x=df["technologie"], y=df["debit_promis_kbps"], marker_color="#0072bc"))
            fig.add_trace(go.Bar(name="Measured rate", x=df["technologie"], y=df["debit_mesure_kbps"], marker_color="#1478c8"))
            fig.update_layout(**plot_layout(360), barmode="group", legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No rate comparison available.")
    with a2:
        data = api("/stats/compliance-by-technician")
        if data:
            df = pd.DataFrame(data).sort_values("taux_conformite", ascending=True).tail(15)
            fig = go.Figure(go.Bar(x=df["taux_conformite"], y=df["id_technicien"], orientation="h", marker_color="#1e9e6b", text=[f"{v}%" for v in df["taux_conformite"]], textposition="inside"))
            fig.update_layout(**plot_layout(360))
            fig.update_xaxes(range=[0, 105], gridcolor="rgba(255,255,255,0.07)", zeroline=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune performance technicien disponible.")

    section_title("Anomalies par technicien", "cyan")
    data = api("/stats/anomalies-by-technician")
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)

with selected[4]:
    section_title("Work-order map — Tunis")
    data = api("/stats/work-orders-by-place")
    if data:
        df = pd.DataFrame(data)
        df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
        df["traitees"] = pd.to_numeric(df["traitees"], errors="coerce").fillna(0)
        df["en_cours"] = pd.to_numeric(df["en_cours"], errors="coerce").fillna(0)
        df["emises"] = pd.to_numeric(df["emises"], errors="coerce").fillna(0)
        df["taux_resolution"] = pd.to_numeric(df["taux_resolution"], errors="coerce").fillna(0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Zones", len(df))
        c2.metric("Work orders", int(df["total"].sum()))
        c3.metric("Average rate", f"{round(df['taux_resolution'].mean(), 1)}%")
        c4.metric("Zone active", df.loc[df["total"].idxmax(), "zone"])

        tech = st.selectbox("Filter by technology", ["All", "ADSL", "VDSL", "GPON"])
        filtered = df if tech == "All" else df[df["technologie"] == tech]
        if filtered.empty:
            st.info("No data for this technology.")
            st.stop()

        filtered = filtered.copy()
        filtered["marker_color"] = filtered["taux_resolution"].apply(
            lambda value: "#1e9e6b" if value >= 70 else "#d97706" if value >= 50 else "#dc3545"
        )
        filtered["marker_size"] = filtered["total"].apply(lambda value: max(12, min(44, value * 2.4)))
        filtered["hover"] = filtered.apply(
            lambda row: (
                f"<b>{row['zone']}</b><br>"
                f"Technology: {row['technologie']}<br>"
                f"Total: {int(row['total'])}<br>"
                f"Processed: {int(row['traitees'])}<br>"
                f"En cours: {int(row['en_cours'])}<br>"
                f"Issued: {int(row['emises'])}<br>"
                f"Resolution rate: {row['taux_resolution']}%"
            ),
            axis=1,
        )

        section_title("Interactive zone map", "cyan")
        fig = go.Figure()
        fig.add_trace(go.Scattergeo(
            lat=filtered["lat"],
            lon=filtered["lon"],
            mode="markers+text",
            text=filtered["zone"],
            textposition="top center",
            textfont=dict(color="#eef2f6", size=9),
            marker=dict(
                size=filtered["marker_size"],
                color=filtered["marker_color"],
                opacity=0.86,
                line=dict(width=1.4, color="rgba(255,255,255,0.42)"),
            ),
            hovertext=filtered["hover"],
            hovertemplate="%{hovertext}<extra></extra>",
            showlegend=False,
        ))
        fig.update_layout(
            height=560,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#fff"),
            geo=dict(
                projection_type="mercator",
                lonaxis=dict(range=[10.145, 10.235], showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
                lataxis=dict(range=[36.755, 36.825], showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
                bgcolor="rgba(0,0,0,0)",
                showland=True,
                landcolor="#141b26",
                showocean=True,
                oceancolor="#0a0e14",
                showlakes=True,
                lakecolor="#0a0e14",
                showcountries=False,
                showcoastlines=False,
                showframe=False,
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            """
            <div style="display:flex;gap:24px;flex-wrap:wrap;margin:8px 0 20px;">
                <span style="color:#1e9e6b;font-size:0.82rem;">● Resolution >= 70%</span>
                <span style="color:#d97706;font-size:0.82rem;">● Resolution 50-70%</span>
                <span style="color:#dc3545;font-size:0.82rem;">● Resolution < 50%</span>
                <span style="color:#8b9aad;font-size:0.82rem;">Point size = work-order volume</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        map_col1, map_col2 = st.columns(2)
        with map_col1:
            section_title("Top lieux — volume")
            df_top = filtered.sort_values("total", ascending=True).tail(10)
            fig2 = go.Figure(go.Bar(
                x=df_top["total"],
                y=df_top["zone"],
                orientation="h",
                marker_color="#0072bc",
                text=df_top["total"].astype(int),
                textposition="outside",
            ))
            fig2.update_layout(**plot_layout(320), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        with map_col2:
            section_title("Resolution rate")
            rate_frame = filtered.sort_values("taux_resolution", ascending=True).tail(10)
            fig3 = go.Figure(go.Bar(
                x=rate_frame["taux_resolution"],
                y=rate_frame["zone"],
                orientation="h",
                marker_color=rate_frame["marker_color"],
                text=[f"{value}%" for value in rate_frame["taux_resolution"]],
                textposition="inside",
            ))
            fig3.update_layout(**plot_layout(320), showlegend=False)
            fig3.update_xaxes(range=[0, 105], gridcolor="rgba(255,255,255,0.07)", zeroline=False)
            st.plotly_chart(fig3, use_container_width=True)

        section_title("Detail per place")
        st.dataframe(filtered.sort_values("total", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("No geographic data available.")

with selected[5]:
    section_title("Logs et anomalies")

    log_col1, log_col2, log_col3 = st.columns([1, 1, 4])
    with log_col1:
        status_value = st.selectbox("Status", ["All", "ANOMALIE", "OK"], key="logs_statut")
    with log_col2:
        log_limit = st.number_input("Nombre", 10, 500, 100, step=10, key="logs_limit")

    logs_endpoint = f"/logs?limit={log_limit}" + (f"&statut_test={status_value}" if status_value != "All" else "")
    logs_data = api(logs_endpoint)

    if logs_data:
        df_logs = pd.DataFrame(logs_data)
        total_logs = len(df_logs)
        anomalies_count = int((df_logs.get("statut_test", pd.Series(dtype=str)) == "ANOMALIE").sum()) if "statut_test" in df_logs else total_logs
        today_count = int(df_logs.get("date_test", pd.Series(dtype=str)).astype(str).str.contains(datetime.now().strftime("%Y-%m-%d"), na=False).sum()) if "date_test" in df_logs else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Logs loaded", total_logs)
        k2.metric("Anomalies", anomalies_count)
        k3.metric("Aujourd'hui", today_count)
        k4.metric("Filtered status", status_value)

        st.markdown("<br>", unsafe_allow_html=True)
        section_title("Recent alerts", "cyan")

        for _, item in df_logs.head(8).iterrows():
            ref = item.get("ref_demande", "N/A")
            status_value = item.get("statut_test", "N/A")
            message = item.get("message_log", "")
            date_value = item.get("date_test", "")
            color = "#dc3545" if status_value == "ANOMALIE" else "#1e9e6b"
            st.markdown(
                f"""
                <div style="border:1px solid rgba(255,255,255,.075);border-left:3px solid {color};background:#10161c;border-radius:10px;padding:14px 16px;margin-bottom:10px;">
                    <div style="display:flex;justify-content:space-between;gap:16px;align-items:center;">
                        <div style="color:#fff;font-weight:750;">{ref}</div>
                        <div style="color:{color};font-size:12px;font-weight:750;">{status_value}</div>
                    </div>
                    <div style="color:#b8c0cc;font-size:13px;line-height:1.45;margin-top:7px;">{message}</div>
                    <div style="color:#6b7686;font-size:12px;margin-top:8px;">{date_value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        section_title("Tableau complet")
        preferred_cols = ["id_log", "ref_demande", "statut_test", "message_log", "date_test"]
        available_cols = [col for col in preferred_cols if col in df_logs.columns]
        if available_cols:
            st.dataframe(df_logs[available_cols], use_container_width=True, hide_index=True, height=420)
        else:
            st.dataframe(df_logs, use_container_width=True, hide_index=True, height=420)
    else:
        st.success("No log available for the selected filter.")

st.caption(f"Last sync: {datetime.now().strftime('%H:%M:%S')} | API: {API_URL}")

# ----------------------------------------------------------------------------
# Floating assistant - rendered outside the tabs so it stays available on
# every page of the dashboard.
# ----------------------------------------------------------------------------
if CHATBOT_PATH.exists():
    try:
        components.html(CHATBOT_PATH.read_text(encoding="utf-8"), height=90, width=90, scrolling=False)
    except Exception:
        pass
