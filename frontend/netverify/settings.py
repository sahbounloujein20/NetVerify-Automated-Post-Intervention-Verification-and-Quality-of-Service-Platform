"""Central configuration of the NetVerify front-end."""

from __future__ import annotations

import os

# ── Application ───────────────────────────────────────────────────────────────
APP_NAME = "NetVerify"
APP_TAGLINE = "Post-intervention verification & quality of service"
ORG_NAME = "Tunisie Telecom"
APP_VERSION = "2.0.0"

# ── Backend ───────────────────────────────────────────────────────────────────
# Overridable by environment variable (essential under Docker, where the backend
# is reachable through its service name and not through 127.0.0.1).
API_URL = os.getenv("NETVERIFY_API_URL", "http://127.0.0.1:8000").rstrip("/")

# Lifetime of the Streamlit caches (seconds).
CACHE_TTL = int(os.getenv("NETVERIFY_CACHE_TTL", "60"))
HEALTH_TTL = 10

# HTTP timeouts (seconds).
TIMEOUT_READ = 8
TIMEOUT_WRITE = 60
TIMEOUT_HEALTH = 2

# ── n8n automation ────────────────────────────────────────────────────────────
# Webhook of the "NetVerify — daily automation" workflow: the D+14 control
# triggered from the interface goes through n8n so it benefits from the retries,
# the execution history and the anomaly e-mail. Set to "" to call the backend
# directly. In containers, n8n lives in its own compose stack and is therefore
# reached through the host (host.docker.internal), not the internal network.
N8N_WEBHOOK_URL = os.getenv(
    "NETVERIFY_N8N_WEBHOOK", "http://127.0.0.1:5678/webhook/netverify-verification"
).strip()

# The workflow retries the backend up to 3 times before giving up: it gets more
# headroom than a direct call.
TIMEOUT_N8N = 90

# ── Business thresholds ───────────────────────────────────────────────────────
# Mandated verification delay after an intervention is closed.
VERIFICATION_DELAY_DAYS = 14

# Compliance objective per technician (%) — materialised by the target line on
# the technician ranking.
COMPLIANCE_TARGET = 90.0

# Bounds of the resolution tiers used on the map and in the tables.
COMPLIANT_THRESHOLD = 70.0
WATCH_THRESHOLD = 50.0

# Technical thresholds — aligned with Backend/comparateur.py so that the
# interface delivers exactly the same verdict as the verification engine.
RATE_TOLERANCE = 0.9   # 90% of the subscribed rate is compliant
SNR_MIN_DB = 6.0              # below this threshold, the line is deemed unstable
ATTENUATION_MAX_DB = 40.0     # beyond it, degraded cable or excessive distance

# ── Referentials ──────────────────────────────────────────────────────────────
TECHNOLOGIES = ["ADSL", "VDSL", "GPON"]

# `ETATS` holds the values stored in `reclamations_workflow.etat_ot`; they are
# never translated. `ETAT_LABELS` maps them to what the operator reads on screen.
STATUSES = ["Emis", "En cours", "Traite"]

STATUS_LABELS = {
    "Emis": "Issued",
    "En cours": "In progress",
    "Traite": "Processed",
}

# Values stored in `journal_actions.resultat`, and what the audit trail shows.
# "refus" is an attempt that authorisation stopped — the most interesting line
# of the journal, hence its own label rather than a lump with the failures.
AUDIT_OUTCOMES = ["All", "succes", "echec", "refus"]

AUDIT_OUTCOME_LABELS = {
    "succes": "Completed",
    "echec": "Failed",
    "refus": "Refused",
}

AUDIT_OUTCOME_TONES = {
    "succes": "good",
    "echec": "critical",
    "refus": "warning",
}

# The privileged endpoints, named for what they do rather than by their path.
AUDIT_ACTION_LABELS = {
    "/verification/run": "D+14 control (manual)",
    "/measurements/verify-compliance": "D+14 control (automated)",
    "/measurements/refresh-all": "Global measurement refresh",
    "/stats/compliance-by-technician": "Compliance per technician",
    "/stats/anomalies-by-technician": "Anomalies per technician",
    "/audit": "Audit trail",
}

# Short month names used on the chart axes. The dictionary keeps its historical
# name; only the labels are in English.
MONTH_LABELS = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}
