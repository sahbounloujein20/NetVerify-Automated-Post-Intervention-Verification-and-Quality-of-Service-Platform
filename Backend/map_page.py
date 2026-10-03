# ══════════════════════════════════════════════════
# TUNIS MAP PAGE — code to be integrated into dashboard.py
# In the sidebar, add "🗺️ Tunis map" to the radio list
# Then append this elif block at the end of the pages
# ══════════════════════════════════════════════════

if page == "🗺️ Tunis map":
    st.markdown('<div class="main-title"><h1>🗺️ WORK-ORDER MAP — TUNIS</h1></div>', unsafe_allow_html=True)

    data = api("/stats/work-orders-by-place")

    if data:
        df_map = pd.DataFrame(data)

        # ── Summary KPIs ──
        km1, km2, km3, km4 = st.columns(4)
        km1.markdown(f'<div class="kpi-card"><div class="kpi-label">Zones covered</div><div class="kpi-value">{len(df_map)}</div></div>', unsafe_allow_html=True)
        km2.markdown(f'<div class="kpi-card"><div class="kpi-label">Total work orders</div><div class="kpi-value">{df_map["total"].sum()}</div></div>', unsafe_allow_html=True)

        busiest_zone = df_map.loc[df_map["total"].idxmax(), "zone"]
        km3.markdown(f'<div class="kpi-card"><div class="kpi-label">Busiest zone</div><div class="kpi-value" style="font-size:1rem;">{busiest_zone}</div></div>', unsafe_allow_html=True)

        average_rate = round(df_map["taux_resolution"].mean(), 1)
        km4.markdown(f'<div class="kpi-card"><div class="kpi-label">Average resolution rate</div><div class="kpi-value">{average_rate}%</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Filter ──
        cf1, cf2 = st.columns([1, 3])
        with cf1:
            technology_choice = st.selectbox("Technology", ["All", "ADSL", "VDSL", "GPON"])

        df_filtered = df_map if technology_choice == "All" else df_map[df_map["technologie"] == technology_choice]

        # ── INTERACTIVE MAP ──
        st.markdown('<div class="section-header">Work orders per location</div>', unsafe_allow_html=True)

        TECH_COLORS = {"ADSL": "#00E5FF", "VDSL": "#FF9800", "GPON": "#4CAF50"}

        fig_map = go.Figure()

        # Circles proportional to the volume
        for _, row in df_filtered.iterrows():
            colour = TECH_COLORS.get(row["technologie"], "#0D6EFD")
            rate = row["taux_resolution"]
            rate_colour = "#4CAF50" if rate >= 70 else "#FF9800" if rate >= 50 else "#F44336"

            fig_map.add_trace(go.Scattermapbox(
                lat=[row["lat"]],
                lon=[row["lon"]],
                mode="markers+text",
                marker=dict(
                    size=max(12, min(40, row["total"] * 2)),
                    color=rate_colour,
                    opacity=0.8,
                ),
                text=[row["zone"]],
                textposition="top center",
                textfont=dict(color="white", size=9),
                hovertemplate=(
                    f"<b>{row['zone']}</b><br>"
                    f"Technology: {row['technologie']}<br>"
                    f"Total: {row['total']}<br>"
                    f"Processed: {row['processed']}<br>"
                    f"In progress: {row['en_cours']}<br>"
                    f"Resolution rate: {rate}%"
                    "<extra></extra>"
                ),
                name=row["zone"],
                showlegend=False,
            ))

        fig_map.update_layout(
            mapbox=dict(
                style="carto-darkmatter",
                center=dict(lat=36.795, lon=10.175),
                zoom=12.5,
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=10, b=0),
            height=520,
            font=dict(color='white'),
        )
        st.plotly_chart(fig_map, use_container_width=True)

        # Colour legend
        st.markdown("""
        <div style="display:flex;gap:24px;margin-top:8px;">
            <span style="color:#4CAF50;font-size:0.8rem;">● Resolution rate ≥ 70%</span>
            <span style="color:#FF9800;font-size:0.8rem;">● Resolution rate 50-70%</span>
            <span style="color:#F44336;font-size:0.8rem;">● Resolution rate < 50%</span>
            <span style="color:#8899BB;font-size:0.8rem;">Circle size = work-order volume</span>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # ── Bar chart per location ──
        cm1, cm2 = st.columns(2)

        with cm1:
            st.markdown('<div class="section-header">Top locations — work-order volume</div>', unsafe_allow_html=True)
            df_top = df_filtered.sort_values("total", ascending=True).tail(10)
            fig2 = go.Figure(go.Bar(
                x=df_top["total"],
                y=df_top["zone"],
                orientation='h',
                marker=dict(
                    color=df_top["total"],
                    colorscale=[[0,"#071A2E"],[0.5,"#0D6EFD"],[1,"#00E5FF"]],
                    showscale=False,
                ),
                text=df_top["total"],
                textposition='outside',
                textfont=dict(color='white', size=11),
            ))
            fig2.update_layout(**layout_plotly(320),
                xaxis=dict(showgrid=True, gridcolor='rgba(13,59,102,0.3)', color='#8899BB'),
                yaxis=dict(showgrid=False, color='#CDD4E0'),
            )
            st.plotly_chart(fig2, use_container_width=True)

        with cm2:
            st.markdown('<div class="section-header">Resolution rate per location (%)</div>', unsafe_allow_html=True)
            rate_frame = df_filtered.sort_values("taux_resolution", ascending=True).tail(10)
            rate_colours = ["#4CAF50" if v >= 70 else "#FF9800" if v >= 50 else "#F44336"
                            for v in rate_frame["taux_resolution"]]
            fig3 = go.Figure(go.Bar(
                x=rate_frame["taux_resolution"],
                y=rate_frame["zone"],
                orientation='h',
                marker_color=rate_colours,
                text=[f"{v}%" for v in rate_frame["taux_resolution"]],
                textposition='inside',
                textfont=dict(color='white', size=11, weight="bold"),
            ))
            fig3.update_layout(**layout_plotly(320),
                xaxis=dict(showgrid=True, gridcolor='rgba(13,59,102,0.3)', color='#8899BB', range=[0,105]),
                yaxis=dict(showgrid=False, color='#CDD4E0'),
            )
            st.plotly_chart(fig3, use_container_width=True)

        st.divider()

        # ── Detailed table ──
        st.markdown('<div class="section-header">Details per location</div>', unsafe_allow_html=True)
        st.dataframe(
            df_filtered[["zone","technologie","total","traitees","en_cours","emises","taux_resolution"]]
            .sort_values("total", ascending=False)
            .rename(columns={
                "zone":"Location", "technologie":"Techno",
                "total":"Total", "traitees":"Processed",
                "en_cours":"In progress", "emises":"Issued",
                "taux_resolution":"Resolution rate (%)"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No geographic data available. Check that the 'zone' column is properly filled in.")
