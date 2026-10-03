"""
dashboard.py — entry point of the NetVerify dashboard (Tunisie Telecom).

This file holds nothing but the application shell: page configuration, theme,
navigation and assistant. Each page lives in `netverify/views/`, the reusable
components in `netverify/ui/`.

Launch:
    python -m streamlit run dashboard.py

Environment variables:
    NETVERIFY_API_URL         backend URL as seen from the Streamlit server
    NETVERIFY_PUBLIC_API_URL  backend URL as seen from the browser (assistant)
    NETVERIFY_CACHE_TTL       lifetime of the data cache, in seconds
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from netverify import auth
from netverify.settings import APP_NAME, APP_TAGLINE, ORG_NAME
from netverify.ui import assistant, shell
from netverify.views import (
    analytics, audit, clients, data_quality, geo, line_quality, logs,
    my_results, operations, overview, work_orders,
)

# Tunisie Telecom drop, identical to the mark in the navigation bar. A generic
# pictogram would make the tab show the same icon as any other application.
# Regenerate with `python assets/make_brand.py`.
FAVICON = Path(__file__).parent / "assets" / "favicon.png"

st.set_page_config(
    page_title=f"{APP_NAME} — {ORG_NAME}",
    page_icon=str(FAVICON) if FAVICON.exists() else ":material/network_check:",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"about": f"{APP_NAME} · {APP_TAGLINE} · {ORG_NAME}"},
)

shell.inject_theme()

# ── Front door ────────────────────────────────────────────────────────────────
# Nothing is mounted until the session is open: no navigation, no page, no
# assistant. A view is therefore not reachable by its URL while bypassing the
# sign-in screen, since no `st.Page` exists yet.
if not auth.require_sign_in():
    st.stop()

# ── Page registry ─────────────────────────────────────────────────────────────
# Sections group the pages; the order fixes that of the chips in the bar.
#
# The registry depends on the role, and the two pages that differ are the two
# nominative ones: Analytics ranks the field agents by name, the audit trail
# names who triggered what. A technician gets "My results" in their place — the
# same figures, but only their own, with the team as an anonymous benchmark.
#
# This is a real gate and not a cosmetic one, for the same reason the sign-in
# screen above is: an unmounted `st.Page` has no URL, so `/analytics` does not
# resolve for a technician instead of resolving and refusing. The backend
# refuses too — the interface only spares a dead end.
supervising = auth.is_supervisor()

ANALYSIS: list = []
if supervising:
    ANALYSIS.append(
        st.Page(analytics.render, title="Analytics",
                icon=":material/insights:", url_path="analytics")
    )
else:
    ANALYSIS.append(
        st.Page(my_results.render, title="My results",
                icon=":material/person_check:", url_path="my-results")
    )

MONITORING: list = [
    st.Page(logs.render, title="Logs",
            icon=":material/receipt_long:", url_path="logs"),
    st.Page(data_quality.render, title="Data quality",
            icon=":material/storage:", url_path="data-quality"),
]
if supervising:
    MONITORING.append(
        st.Page(audit.render, title="Audit trail",
                icon=":material/verified_user:", url_path="audit")
    )

SECTIONS: dict[str, list] = {
    "Steering": [
        st.Page(overview.render, title="Dashboard",
                icon=":material/space_dashboard:", url_path="dashboard", default=True),
    ],
    "Operations": [
        st.Page(clients.render, title="Customers",
                icon=":material/groups:", url_path="customers"),
        st.Page(work_orders.render, title="Work orders",
                icon=":material/assignment:", url_path="work-orders"),
    ],
    "Analysis": [
        *ANALYSIS,
        st.Page(operations.render, title="Performance",
                icon=":material/flag:", url_path="performance"),
        st.Page(line_quality.render, title="Line quality",
                icon=":material/network_check:", url_path="line-quality"),
        st.Page(geo.render, title="Map",
                icon=":material/map:", url_path="map"),
    ],
    "Monitoring": MONITORING,
}

# Native navigation is hidden: the original floating bar plays that role.
current_page = st.navigation(SECTIONS, position="hidden")

shell.render_topnav(SECTIONS, current_page)

current_page.run()

# The assistant is mounted outside the pages so it stays reachable everywhere.
assistant.render()
