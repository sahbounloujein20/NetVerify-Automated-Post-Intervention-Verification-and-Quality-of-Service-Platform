"""
Streamlit dashboard - Network work orders (Greater Tunis)
Displays an interactive map of the work-order zones plus KPIs and filters.

Run with:
    pip install -r requirements.txt
    streamlit run app.py
"""

import pandas as pd
import numpy as np
import pydeck as pdk
import streamlit as st
from place_coords import PLACE_COORDS

st.set_page_config(page_title="Work Orders Dashboard - Tunis", layout="wide")

# ----------------------------------------------------------------------------
# 1. DATA SOURCE
# ----------------------------------------------------------------------------
st.sidebar.title("⚙️ Data connection")
source = st.sidebar.radio(
    "Data source",
    ["PostgreSQL database", "CSV file", "Demonstration data"],
    index=2,
)

@st.cache_data(ttl=300)
def load_from_postgres(host, port, dbname, user, password):
    import sqlalchemy
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    engine = sqlalchemy.create_engine(url)
    query = "SELECT * FROM public.reclamations_workflow ORDER BY ref_demande ASC;"
    return pd.read_sql(query, engine)

@st.cache_data
def load_demo_data():
    """Generates a dummy dataset consistent with the table schema."""
    rng = np.random.default_rng(42)
    n = 500
    fsi_list = ["Hexabyte", "GlobalNet", "FSI TT", "Topnet", "Bee"]
    request_type_list = ["Augmentation", "Migration", "Réclamation", "Dérangement"]
    type_ot_list = ["Changement Profil", "Basculement Port", "Réclamation", "Dérangement"]
    status_list = ["En cours", "Emis", "Traité"]
    zones = list(PLACE_COORDS.keys())

    df = pd.DataFrame({
        "ref_demande": range(1, n + 1),
        "fsi": rng.choice(fsi_list, n),
        "type_demande": rng.choice(request_type_list, n),
        "type_ot": rng.choice(type_ot_list, n),
        "etat_ot": rng.choice(status_list, n),
        "date_etat": pd.to_datetime("2026-05-25") + pd.to_timedelta(rng.integers(0, 25, n), unit="D"),
        "id_technicien": ["TECH-" + str(x).zfill(3) for x in rng.integers(1, 500, n)],
        "zone_reclamation": rng.choice(zones, n),
    })
    return df

df = pd.DataFrame()

if source == "PostgreSQL database":
    with st.sidebar.expander("Connection settings", expanded=True):
        host = st.text_input("Host", "localhost")
        port = st.text_input("Port", "5432")
        dbname = st.text_input("Database", "postgres")
        user = st.text_input("User", "postgres")
        password = st.text_input("Password", type="password")
        connect_btn = st.button("Connect")
    if connect_btn:
        try:
            df = load_from_postgres(host, port, dbname, user, password)
            st.sidebar.success(f"{len(df)} rows loaded ✅")
        except Exception as e:
            st.sidebar.error(f"Connection error: {e}")

elif source == "CSV file":
    uploaded = st.sidebar.file_uploader("Load a CSV export", type=["csv"])
    if uploaded is not None:
        df = pd.read_csv(uploaded)

else:
    df = load_demo_data()
    st.sidebar.info("Demonstration data generated locally.")

if df.empty:
    st.title("📍 Work Orders Dashboard - Greater Tunis")
    st.warning("No data loaded. Choose a source in the side menu.")
    st.stop()

# ----------------------------------------------------------------------------
# 2. PREPROCESSING
# ----------------------------------------------------------------------------
df["date_etat"] = pd.to_datetime(df["date_etat"], errors="coerce")
df["lat"] = df["zone_reclamation"].map(lambda z: PLACE_COORDS.get(z, (None, None))[0])
df["lon"] = df["zone_reclamation"].map(lambda z: PLACE_COORDS.get(z, (None, None))[1])
non_geo = df[df["lat"].isna()]["zone_reclamation"].unique()

# ----------------------------------------------------------------------------
# 3. FILTERS
# ----------------------------------------------------------------------------
st.sidebar.title("🔎 Filters")
fsi_sel = st.sidebar.multiselect("ISP", sorted(df["fsi"].dropna().unique()))
selected_request_type = st.sidebar.multiselect("Request type", sorted(df["type_demande"].dropna().unique()))
selected_status = st.sidebar.multiselect("Work-order status", sorted(df["etat_ot"].dropna().unique()))

if df["date_etat"].notna().any():
    dmin, dmax = df["date_etat"].min().date(), df["date_etat"].max().date()
    date_range = st.sidebar.date_input("Period", (dmin, dmax), min_value=dmin, max_value=dmax)
else:
    date_range = None

filtered = df.copy()
if fsi_sel:
    filtered = filtered[filtered["fsi"].isin(fsi_sel)]
if selected_request_type:
    filtered = filtered[filtered["type_demande"].isin(selected_request_type)]
if selected_status:
    filtered = filtered[filtered["etat_ot"].isin(selected_status)]
if date_range and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    filtered = filtered[(filtered["date_etat"] >= start) & (filtered["date_etat"] <= end)]

# ----------------------------------------------------------------------------
# 4. KPIs
# ----------------------------------------------------------------------------
st.title("📍 Work Orders Dashboard - Greater Tunis")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total work orders", len(filtered))
col2.metric("Active zones", filtered["zone_reclamation"].nunique())
en_cours = (filtered["etat_ot"] == "En cours").sum()
col3.metric("In progress", en_cours)
processed = (filtered["etat_ot"] == "Traité").sum() if "Traité" in filtered["etat_ot"].unique() else (filtered["etat_ot"].str.contains("Trait", case=False, na=False)).sum()
col4.metric("Processed", processed)

st.divider()

# ----------------------------------------------------------------------------
# 5. MAP
# ----------------------------------------------------------------------------
st.subheader("🗺️ Map of the work-order zones")

agg = (
    filtered.dropna(subset=["lat", "lon"])
    .groupby(["zone_reclamation", "lat", "lon"])
    .size()
    .reset_index(name="nb_reclamations")
)

if not agg.empty:
    max_count = agg["nb_reclamations"].max()
    agg["radius"] = 80 + (agg["nb_reclamations"] / max_count) * 400

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=agg,
        get_position=["lon", "lat"],
        get_radius="radius",
        get_fill_color=[220, 60, 60, 160],
        get_line_color=[150, 20, 20],
        line_width_min_pixels=1,
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=agg["lat"].mean(),
        longitude=agg["lon"].mean(),
        zoom=11,
        pitch=0,
    )

    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            map_style="mapbox://styles/mapbox/light-v9",
            tooltip={"text": "{zone_reclamation}\n{nb_reclamations} work order(s)"},
        )
    )
else:
    st.info("No geolocated data to display for these filters.")

if len(non_geo) > 0:
    st.caption(f"⚠️ Zones with no known coordinates (ignored on the map): {', '.join(non_geo)}")

st.divider()

# ----------------------------------------------------------------------------
# 6. CHARTS & TABLE
# ----------------------------------------------------------------------------
c1, c2 = st.columns(2)

with c1:
    st.subheader("Work orders per zone")
    st.bar_chart(
        filtered["zone_reclamation"].value_counts().sort_values(ascending=False)
    )

with c2:
    st.subheader("Breakdown by work-order status")
    st.bar_chart(filtered["etat_ot"].value_counts())

st.subheader("📋 Work-order details")
st.dataframe(
    filtered[
        ["ref_demande", "fsi", "type_demande", "type_ot", "etat_ot",
         "date_etat", "id_technicien", "zone_reclamation"]
    ] if "ref_demande" in filtered.columns else filtered,
    use_container_width=True,
    height=350,
)
