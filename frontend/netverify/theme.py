"""
NetVerify design system — a faithful reprise of the original visual identity.

Every colour comes from the first version of the dashboard: background
`#0a0e14`, panels `#10161c`, Tunisie Telecom accent `#0072bc`, green `#1e9e6b`,
amber `#d97706`, red `#dc3545`. The rest of the front-end consumes these tokens;
changing a value here changes it everywhere.

What was corrected without touching the identity
------------------------------------------------
* The two near-identical blues (`#0072bc` / `#1478c8`) were not being used to
  distinguish two series: the accent + amber pair, both already present in the
  original palette, is used instead (ΔE 24.7 under protanopia).
* Two colours failed the contrast requirement for small text on a panel: the red
  `#dc3545` (4.02:1) and the light blue `#1478c8` (3.94:1). They stay as they are
  for the chart marks; the text uses lightened variants (`#f47b86` at 6.96:1,
  `#5aa9dc` at 7.06:1).
* The map tiers (green / amber / red) merge under deuteranopia (ΔE 5.6) and the
  amber-red pair stays difficult even in normal vision (ΔE 14.3). The original
  hue is kept, but it no longer carries the meaning on its own: marker shape,
  legend label and a numeric tooltip do too.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

# ══════════════════════════════════════════════════════════════════════════════
# 1. TOKENS — taken from v1
# ══════════════════════════════════════════════════════════════════════════════

PLANE = "#0a0e14"        # application background
SURFACE = "#10161c"      # panel / chart surface
SURFACE_2 = "#141b26"    # fields, raised elements
SURFACE_3 = "#1a2431"    # hover, table headers
LINE = "rgba(255,255,255,0.08)"
LINE_STRONG = "rgba(255,255,255,0.14)"
LINE_ACCENT = "rgba(0,114,188,0.35)"

# Ink (contrasts measured on SURFACE: 16.2 / 8.9 / 6.4)
INK = "#eef2f6"
INK_2 = "#b8c0cc"
INK_3 = "#8b9aad"

# Tunisie Telecom brand
BRAND = "#0072bc"
BRAND_600 = "#005a96"
BRAND_400 = "#1478c8"
BRAND_300 = "#5aa9dc"    # variant readable in small text (7.06:1)

# Categorical palette — accent, amber, green, sky, red: only hues already
# present in the original mock-up.
SERIES = [
    "#0072bc",  # 1 accent
    "#d97706",  # 2 amber
    "#1e9e6b",  # 3 green
    "#5aa9dc",  # 4 sky
    "#dc3545",  # 5 red
]

# Statuses — a reserved set, never used as a series identity.
STATUS = {
    "good": "#1e9e6b",
    "warning": "#d97706",
    "serious": "#e0803c",
    "critical": "#dc3545",
}

# Text variants: only the red had to be lightened to stay readable.
STATUS_TEXT = {
    "good": "#1e9e6b",
    "warning": "#d97706",
    "serious": "#e0803c",
    "critical": "#f47b86",
}

# Workflow status colours — identical to the v1 donut. The keys are the values
# stored in `etat_ot` and are therefore never translated.
STATUS_COLORS = {
    "Emis": "#0072bc",
    "En cours": "#d97706",
    "Traite": "#1e9e6b",
}

# Sequential ramp — a single hue (the brand blue), from darkest to lightest.
# Reserved for continuous quantities: heat matrices, densities.
#
# Two constraints fixed the bounds. At the bottom, the first step stays close to
# the surface so that a low value does not shout. At the top, the ramp stops at
# `BRAND_400` and not at `BRAND_300`: the cells carry their value written in
# light ink, which would drop to 2.4:1 on a brighter background. At the chosen
# step, the text contrast stays at 4.5:1.
SEQUENTIAL = [
    "#101a22", "#10263a", "#0f3d5e", "#0d5286", "#0f68aa", "#1478c8",
]

# Chart chrome — original grid
GRID = "rgba(255,255,255,0.07)"
AXIS = "rgba(255,255,255,0.12)"

RADIUS = "12px"
RADIUS_SM = "10px"
FONT_STACK = (
    'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, '
    '"Segoe UI", sans-serif'
)


def status_of(rate: float) -> str:
    """Status tier corresponding to a resolution rate (%)."""
    from .settings import COMPLIANT_THRESHOLD, WATCH_THRESHOLD

    if rate >= COMPLIANT_THRESHOLD:
        return "good"
    if rate >= WATCH_THRESHOLD:
        return "warning"
    return "critical"


# ══════════════════════════════════════════════════════════════════════════════
# 2. CSS VARIABLES
# ══════════════════════════════════════════════════════════════════════════════

_VARS = {
    "--bg": PLANE,
    "--panel": SURFACE,
    "--panel-2": SURFACE_2,
    "--panel-3": SURFACE_3,
    "--line": LINE,
    "--line-strong": LINE_STRONG,
    "--line-accent": LINE_ACCENT,
    "--text": INK,
    "--text-2": INK_2,
    "--muted": INK_3,
    "--accent": BRAND,
    "--accent-2": BRAND_400,
    "--accent-3": BRAND_300,
    "--green": STATUS["good"],
    "--amber": STATUS["warning"],
    "--red": STATUS["critical"],
    "--red-text": STATUS_TEXT["critical"],
    "--radius": RADIUS,
    "--radius-sm": RADIUS_SM,
    "--font": FONT_STACK,
}


def css_variables() -> str:
    body = "\n".join(f"  {k}: {v};" for k, v in _VARS.items())
    return f":root {{\n{body}\n}}"


# ══════════════════════════════════════════════════════════════════════════════
# 3. STYLESHEET
# ══════════════════════════════════════════════════════════════════════════════

STYLESHEET = """
/* ── Base ─────────────────────────────────────────────────────────────────── */
html, body, .stApp,
[data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"] { font-family: var(--font); }

/* Streamlit's Material icons render as ligatures: their font must stay intact,
   otherwise it is the glyph name ("space_dashboard", "refresh") that appears
   spelled out on top of the label. */
[data-testid="stIconMaterial"], .material-symbols-rounded, .nv-icon {
    font-family: "Material Symbols Rounded" !important;
    font-weight: normal; font-style: normal; letter-spacing: normal;
    text-transform: none; white-space: nowrap; word-wrap: normal; direction: ltr;
    font-feature-settings: "liga"; -webkit-font-feature-settings: "liga";
    -webkit-font-smoothing: antialiased;
    display: inline-flex; align-items: center; justify-content: center;
    line-height: 1; flex: 0 0 auto;
}
/* Icons in our own HTML blocks: a closed 1 em box. Were a ligature missing, its
   name would be clipped instead of spilling over the neighbouring text. */
.nv-icon { width: 1em; height: 1em; overflow: hidden; }

.stApp {
    background:
        radial-gradient(circle at 20% -10%, rgba(0,114,188,0.14), transparent 32%),
        radial-gradient(circle at 80% -6%, rgba(20,120,200,0.08), transparent 30%),
        var(--bg);
    color: var(--text);
}
[data-testid="stMainBlockContainer"] { padding: 1.35rem 1.65rem 3.5rem; max-width: 1440px; }
[data-testid="stAppHeader"], header[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"], [data-testid="stAppDeployButton"],
[data-testid="stMainMenu"], footer, [data-testid="stDecoration"] { display: none !important; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapseButton"],
[data-testid="stExpandSidebarButton"] { display: none !important; }

h1, h2, h3, h4 { font-family: var(--font); color: var(--text); }
a { color: var(--accent-3); }
hr { border-color: var(--line); }

::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #222c38; border-radius: 8px; border: 2px solid var(--bg); }
::-webkit-scrollbar-thumb:hover { background: #2e3c4c; }

/* ── Barre de navigation flottante ────────────────────────────────────────── */
[class*="st-key-nvtopnav"] {
    width: min(1140px, 100%);
    margin: 0 auto 1.15rem;
    padding: 10px 18px;
    border: 1px solid var(--line);
    border-radius: 20px;
    background: rgba(10, 14, 20, 0.92);
    box-shadow: 0 20px 55px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04);
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 178px; }

/* The operator's drop, in place of the former NV badge. Only the height is
   set: the mark is 1.51 times wider than tall and a fixed square would
   squeeze it. `logo-fallback` covers a checkout where `make_brand.py` has
   never been run — a readable badge rather than a broken image icon. */
.brand-mark { height: 34px; width: auto; flex: none; display: block; }
.logo-fallback {
    aspect-ratio: 115 / 76; border-radius: 9px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    box-shadow: 0 2px 10px rgba(0,114,188,0.35);
    display: grid; place-items: center; color: #fff; font-weight: 800; font-size: 13px;
}
.brand-name { font-weight: 850; letter-spacing: 0; line-height: 1; font-size: 16px; }
.brand-name span { color: var(--accent-2); }
.brand-sub { color: #6b7686; font-size: 10px; font-weight: 700; letter-spacing: .11em; margin-top: 3px; }

/* The navigation chips are real buttons: the top bar is now the navigation
   itself, and not a decoration doubled by a row of tabs. */
[class*="st-key-nvchips"] { flex-wrap: wrap; row-gap: 4px; }
[class*="st-key-nvchips"] [data-testid="stIconMaterial"] { font-size: 18px; }
.stButton [data-testid="stIconMaterial"] { font-size: 18px; }

[class*="st-key-nvchips"] .stButton > button {
    display: inline-flex; align-items: center; gap: 7px;
    background: transparent; border: 1px solid transparent; box-shadow: none;
    color: #7c8798; font-weight: 700; font-size: 14px;
    padding: 9px 13px; min-height: 0; white-space: nowrap;
    transition: color .15s ease, background .15s ease;
}
[class*="st-key-nvchips"] .stButton > button:hover {
    color: #cfd6de; background: rgba(255,255,255,0.04);
    border-color: transparent; transform: none;
}
[class*="st-key-nvchips"] .stButton > button p { font-weight: 700; }

[class*="st-key-nvactivechip"] .stButton > button,
[class*="st-key-nvactivechip"] .stButton > button:hover {
    color: #fff;
    background: linear-gradient(90deg, rgba(0,114,188,0.24), rgba(20,120,200,0.14));
    border-color: rgba(0,114,188,0.32);
    box-shadow: inset 0 -2px 0 var(--accent);
}
[class*="st-key-nvactivechip"] .stButton > button * { color: #fff !important; }

/* ── Session identity ─────────────────────────────────────────────────────── */
.user-pill {
    display: flex; align-items: center; gap: 9px; white-space: nowrap;
    padding-left: 14px; border-left: 1px solid var(--line);
}
.user-avatar {
    width: 30px; height: 30px; border-radius: 999px; flex: 0 0 30px;
    display: grid; place-items: center;
    background: var(--panel-3); border: 1px solid var(--line-strong);
    color: var(--accent-3); font-size: 11px; font-weight: 800; letter-spacing: .02em;
}
.user-meta { display: flex; flex-direction: column; line-height: 1.15; }
.user-name { color: var(--text-2); font-size: 12.5px; font-weight: 700; }
/* The role decides what the user can trigger: it is displayed permanently, and
   not hidden in a menu, so that a refused action is never a surprise. */
.user-role { color: #6b7686; font-size: 10.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
/* A supervisor carries privileges a technician does not: the accent makes the
   two sessions distinguishable at a glance, side by side on a screen. */
.user-role.sup { color: var(--accent-3); }

/* ── Sign-in screen ───────────────────────────────────────────────────────── */
.login-head { text-align: center; margin: 8vh 0 22px; }
.login-logo { height: 78px; width: auto; display: block; margin: 0 auto 18px; }
.login-head h1 { font-size: 26px; font-weight: 850; color: var(--text); margin: 0 0 6px; }
.login-head p { color: var(--muted); font-size: 13.5px; margin: 0 0 10px; }
.login-org { color: #6b7686; font-size: 10.5px; font-weight: 700; letter-spacing: .13em; }
.login-note {
    color: #6b7686; font-size: 11.5px; line-height: 1.6; text-align: center;
    margin-top: 18px; padding: 0 6px;
}
.login-note code {
    background: var(--panel-2); border: 1px solid var(--line);
    border-radius: 5px; padding: 1px 5px; font-size: 11px; color: var(--text-2);
}

/* ── Bandeau d'accueil ────────────────────────────────────────────────────── */
.hero {
    min-height: 220px;
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)), var(--panel);
    border-radius: var(--radius);
    display: grid; place-items: center; text-align: center;
    margin: 4px 0 30px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.035);
}
.hero-logo { height: 84px; width: auto; display: block; margin: 0 auto 20px; }
.hero h1 { margin: 0; font-size: clamp(26px, 3vw, 38px); font-weight: 800; }
.hero p { margin: 10px 0 0; color: var(--muted); font-size: 16px; }
.hero-meta { margin-top: 18px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }

/* ── Page header (pages other than the home page) ─────────────────────────── */
.pagehead { display: flex; align-items: flex-start; gap: 14px; margin: 2px 0 20px; }
.pagehead-icon {
    width: 44px; height: 44px; flex: 0 0 44px; border-radius: var(--radius); display: grid; place-items: center;
    background: rgba(0,114,188,.15); color: var(--accent-3);
}
.pagehead h1 { margin: 0; font-size: 26px; font-weight: 800; line-height: 1.2; }
.pagehead p { margin: 6px 0 0; color: var(--muted); font-size: 14px; line-height: 1.5; max-width: 82ch; }

/* ── Cartes ───────────────────────────────────────────────────────────────── */
[class*="st-key-nvcard"] {
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.028), rgba(255,255,255,0.012)), var(--panel);
    border-radius: var(--radius);
    padding: 22px 24px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
}
[class*="st-key-nvcard"] [class*="st-key-nvcard"] { box-shadow: none; }

.panel-title {
    color: var(--text); font-size: 18px; font-weight: 750; margin: 0 0 6px;
    display: flex; align-items: center; gap: 10px;
}
.panel-title .accent { color: var(--accent-2); }
.panel-title .cyan { color: var(--accent-3); }
.panel-sub { color: var(--muted); font-size: 13px; line-height: 1.5; margin: 0 0 16px; }
.panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.panel-aside { color: var(--muted); font-size: 12.5px; white-space: nowrap; font-variant-numeric: tabular-nums; padding-top: 4px; }

/* ── Key-figure tiles (anatomy of the v1 cards) ───────────────────────────── */
.kpi-grid {
    display: grid; gap: 18px;
    grid-template-columns: repeat(auto-fit, minmax(248px, 1fr));
    margin-bottom: 4px;
}
.card {
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.028), rgba(255,255,255,0.012)), var(--panel);
    border-radius: var(--radius);
    padding: 22px 24px;
    min-height: 154px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
    display: flex; flex-direction: column;
}
.card:hover {
    transform: translateY(-2px);
    border-color: rgba(0,114,188,0.32);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 12px 28px rgba(0,0,0,0.28);
}
.card-title {
    display: flex; align-items: center; gap: 12px;
    color: var(--text); font-weight: 750; font-size: 15px; margin-bottom: 18px;
}
.card-icon { width: 44px; height: 44px; flex: 0 0 44px; display: grid; place-items: center; border-radius: var(--radius); }
.icon-primary { background: rgba(0,114,188,.15); color: var(--accent-3); }
.icon-green   { background: rgba(30,158,107,.14); color: var(--green); }
.icon-amber   { background: rgba(217,119,6,.14);  color: var(--amber); }
.icon-red     { background: rgba(220,53,69,.14);  color: var(--red-text); }
.icon-neutral { background: rgba(139,154,173,.14); color: var(--muted); }

.kpi-row { display: flex; gap: 30px; flex-wrap: wrap; align-items: baseline; }
.kpi-value { color: #fff; font-size: 28px; font-weight: 800; line-height: 1; }
.kpi-unit { font-size: 15px; font-weight: 700; color: var(--text-2); margin-left: 3px; }
.kpi-label { color: var(--muted); font-size: 13px; margin-top: 8px; display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.kpi-delta { display: inline-flex; align-items: center; gap: 4px; font-weight: 750; font-variant-numeric: tabular-nums; }
/* Trend drawn with CSS bars (see cards.sparkline: SVG does not survive the
   sanitising of st.html). */
.spark { display: flex; align-items: flex-end; gap: 3px; margin-top: auto; }
.spark i { flex: 1 1 0; min-width: 2px; min-height: 2px; border-radius: 2px 2px 0 0; }

.meter { margin-top: auto; padding-top: 14px; }
.meter-track { height: 6px; border-radius: 999px; background: rgba(255,255,255,.07); overflow: hidden; }
.meter-fill { height: 100%; border-radius: 999px; }
.meter-scale { display: flex; justify-content: space-between; margin-top: 6px; font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }

/* ── Badges ───────────────────────────────────────────────────────────────── */
.badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 700; line-height: 1.6;
    border: 1px solid transparent; white-space: nowrap;
}
.badge .dot { width: 6px; height: 6px; border-radius: 999px; flex: 0 0 6px; }
.badge.good     { background: rgba(30,158,107,.14); border-color: rgba(30,158,107,.32); color: var(--green); }
.badge.warning  { background: rgba(217,119,6,.13);  border-color: rgba(217,119,6,.32);  color: var(--amber); }
.badge.critical { background: rgba(220,53,69,.13);  border-color: rgba(220,53,69,.34);  color: var(--red-text); }
.badge.brand,
.badge.info     { background: rgba(0,114,188,.15);  border-color: rgba(0,114,188,.34);  color: var(--accent-3); }
.badge.neutral  { background: rgba(255,255,255,.05); border-color: var(--line); color: var(--muted); }

/* ── Chart legend ─────────────────────────────────────────────────────────── */
.legend { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0 0 12px; }
.legend-item { display: inline-flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-2); }
.legend-mark { width: 10px; height: 10px; flex: 0 0 10px; display: grid; place-items: center; }
.legend-note { font-size: 12.5px; color: var(--muted); }

/* ── Fil d'alertes ────────────────────────────────────────────────────────── */
.feed { display: flex; flex-direction: column; }
.feed-item {
    border: 1px solid rgba(255,255,255,.075);
    border-left: 3px solid var(--red);
    background: var(--panel);
    border-radius: var(--radius-sm);
    padding: 13px 15px; margin-bottom: 10px;
}
.feed-item:last-child { margin-bottom: 0; }
.feed-head { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.feed-ref { color: #fff; font-weight: 750; font-size: 13.5px; }
.feed-msg {
    color: var(--text-2); font-size: 13px; line-height: 1.45; margin-top: 7px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.feed-time { color: #6b7686; font-size: 12px; margin-top: 8px; font-variant-numeric: tabular-nums; }

/* ── Empty / error states ─────────────────────────────────────────────────── */
.empty {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    text-align: center; padding: 34px 22px; gap: 4px;
    border: 1px dashed rgba(255,255,255,.14); border-radius: var(--radius);
    background: rgba(255,255,255,.015);
}
.empty-icon {
    width: 44px; height: 44px; border-radius: var(--radius); display: grid; place-items: center;
    background: rgba(255,255,255,.04); margin-bottom: 8px; color: var(--muted);
}
.empty h4 { margin: 0; font-size: 15px; font-weight: 750; color: var(--text-2); }
.empty p { margin: 4px 0 0; font-size: 13px; color: var(--muted); max-width: 48ch; line-height: 1.5; }

.banner {
    display: flex; align-items: flex-start; gap: 12px;
    border-radius: var(--radius); padding: 14px 16px; margin-bottom: 18px;
    border: 1px solid rgba(220,53,69,.34); background: rgba(220,53,69,.09);
}
.banner-title { font-size: 14px; font-weight: 750; color: var(--red-text); }
.banner-text { font-size: 13px; color: var(--text-2); margin-top: 4px; line-height: 1.55; }
.banner code { background: rgba(255,255,255,.06); padding: 1px 6px; border-radius: 5px; font-size: 12px; color: var(--text); }

/* ── Detail sheet ─────────────────────────────────────────────────────────── */
.kv { display: grid; grid-template-columns: repeat(auto-fit, minmax(158px, 1fr)); gap: 16px 22px; }
.kv-key { font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.kv-val { font-size: 14.5px; font-weight: 650; color: var(--text); margin-top: 5px; overflow-wrap: anywhere; }

/* ── Widgets Streamlit ────────────────────────────────────────────────────── */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: var(--radius-sm);
    border: 1px solid rgba(0,114,188,0.32);
    background: linear-gradient(90deg, rgba(0,114,188,0.16), rgba(20,120,200,0.1));
    color: #fff; font-weight: 700; font-size: 13.5px; min-height: 40px;
    transition: border-color .15s ease, background .15s ease, transform .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
    border-color: var(--accent); color: #fff;
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
    transform: translateY(-1px);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
    border-color: rgba(255,255,255,.14);
}
.stButton > button[kind="primary"]:hover { filter: brightness(1.1); }

.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div,
.stTextInput input, .stNumberInput input, .stDateInput input {
    background: var(--panel-2) !important;
    border-color: var(--line-strong) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text) !important;
    font-size: 13.5px !important;
}
.stSelectbox label, .stMultiSelect label, .stTextInput label,
.stNumberInput label, .stDateInput label, .stSlider label, .stRadio label {
    font-size: 12px !important; font-weight: 700 !important;
    color: var(--muted) !important;
}
[data-baseweb="popover"] li { font-size: 13.5px; }

[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: var(--radius-sm); overflow: hidden; }
[data-testid="stDataFrame"] * { font-variant-numeric: tabular-nums; }

.stTabs [data-baseweb="tab-list"] { gap: 8px; justify-content: center; margin-bottom: 18px; }
.stTabs [data-baseweb="tab"] {
    border-radius: var(--radius-sm); padding: 8px 16px; color: #7c8798; font-weight: 700;
    background: transparent; border: 1px solid transparent;
}
.stTabs [aria-selected="true"] {
    color: #fff; background: linear-gradient(90deg, rgba(0,114,188,.22), rgba(20,120,200,.12));
    border-color: rgba(0,114,188,.28);
}

[data-testid="stExpander"] details {
    border: 1px solid var(--line); border-radius: var(--radius-sm);
    background: rgba(255,255,255,.015);
}
[data-testid="stExpander"] summary { font-size: 13px; font-weight: 700; color: var(--muted); }
[data-testid="stExpander"] summary:hover { color: var(--text); }

[data-testid="stAlert"] { border-radius: var(--radius-sm); border: 1px solid var(--line); }
[data-testid="stCaptionContainer"] p { color: var(--muted); font-size: 12px; }
.stPlotlyChart { border-radius: var(--radius-sm); overflow: hidden; }
.js-plotly-plot .plotly .modebar { background: transparent !important; }
.js-plotly-plot .plotly .modebar-btn path { fill: var(--muted) !important; }
.js-plotly-plot .plotly .modebar-btn:hover path { fill: var(--text) !important; }

/* ── Responsive ───────────────────────────────────────────────────────────── */
@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] { padding: 1rem 1rem 3rem; }
    [class*="st-key-nvtopnav"] { border-radius: 16px; }
    .user-pill { border-left: 0; padding-left: 0; }
    .hero { min-height: 200px; }
    .kpi-value { font-size: 25px; }
}
"""


def full_css() -> str:
    return f"<style>\n{css_variables()}\n{STYLESHEET}\n</style>"


# ══════════════════════════════════════════════════════════════════════════════
# 4. TEMPLATE PLOTLY
# ══════════════════════════════════════════════════════════════════════════════

TEMPLATE_NAME = "netverify"


def register_plotly_template() -> None:
    """Registers and activates the in-house Plotly template (idempotent)."""
    if TEMPLATE_NAME in pio.templates:
        pio.templates.default = TEMPLATE_NAME
        return

    axis = dict(
        gridcolor=GRID,
        griddash="solid",
        gridwidth=1,
        zeroline=False,
        linecolor=AXIS,
        linewidth=1,
        ticks="outside",
        ticklen=4,
        tickcolor=AXIS,
        tickfont=dict(color=INK_3, size=11.5),
        title=dict(font=dict(color=INK_3, size=11.5)),
        automargin=True,
    )

    pio.templates[TEMPLATE_NAME] = go.layout.Template(
        layout=dict(
            colorway=SERIES,
            font=dict(family=FONT_STACK, color=INK_2, size=12.5),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=8, r=14, t=10, b=8),
            xaxis={**axis, "showgrid": False},
            yaxis=axis,
            hoverlabel=dict(
                bgcolor=SURFACE_3,
                bordercolor=LINE_STRONG,
                font=dict(family=FONT_STACK, color=INK, size=12.5),
                align="left",
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                x=0,
                bgcolor="rgba(0,0,0,0)",
                font=dict(color=INK_2, size=12),
                itemsizing="constant",
                itemwidth=30,
            ),
            separators=", ",
            dragmode=False,
        )
    )
    pio.templates.default = TEMPLATE_NAME
