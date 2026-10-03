# NetVerify — Front-end

Streamlit dashboard of the NetVerify platform (Tunisie Telecom): work-order
follow-up, D+14 compliance control and quality-of-service steering.

```bash
python -m streamlit run dashboard.py
```

The FastAPI backend must be running alongside (`Backend/` → `python -m uvicorn main:app --reload`).
Without it the application stays usable: every page shows an explicit offline
state instead of empty tables.

## Architecture

```
frontend/
├── dashboard.py              Entry point: page config, theme, navigation, assistant
├── chatbot.html              Floating assistant widget (repositioned iframe)
├── .streamlit/config.toml    Native widget theme (aligned with theme.py)
├── assets/
│   ├── make_brand.py         Generator of the Tunisie Telecom mark + favicon
│   ├── tt-logo.svg           Full lockup — drop + TT + "Tunisie Telecom"
│   ├── tt-mark.svg           Drop + TT alone, for the navigation bar
│   └── favicon.png           256 px raster of the mark (browser tab)
└── netverify/
    ├── settings.py           API URL, cache TTL, business thresholds
    ├── theme.py              Design tokens, stylesheet, Plotly template
    ├── brand.py              The mark, inlined into the headers as a data URI
    ├── api.py                Typed HTTP client (Result: ok / empty / error)
    ├── utils.py              Formatting (numbers, %, rates, dates)
    ├── ui/
    │   ├── shell.py          Floating navigation bar, banner, cards, sections
    │   ├── cards.py          KPI tiles, sparklines, gauges, badges, alert feed
    │   ├── charts.py         Plotly builders (columns, bars, donut, areas,
    │   │                     histogram, P10–P90 dumbbells, scatter, Pareto, matrix)
    │   ├── tables.py         Configured tables, search, CSV export
    │   ├── states.py         Empty / error / backend-offline states
    │   ├── icons.py          Embedded SVG icon set
    │   └── assistant.py      Mounting of the conversational widget
    └── views/                One business page per module
        ├── overview.py       Overview
        ├── work_orders.py    Work-order follow-up + D+14 control trigger
        ├── clients.py        Customer estate + NetScan technical sheet
        ├── analytics.py      Rate gaps, nominative technician ranking (supervisor)
        ├── my_results.py     Own results + anonymous benchmark (technician)
        ├── operations.py     Backlog ageing, smoothed flow, ISP matrix, Pareto
        ├── line_quality.py   NetScan distributions, percentiles, diagnostic scatter
        ├── data_quality.py   Volumetry, freshness, completeness, integrity
        ├── geo.py            Zone cartography
        ├── logs.py           Control journal
        └── audit.py          Privileged-action journal (supervisor)
```

Dependency rule: `views/` → `ui/` → `theme` + `utils`. A view never builds HTML
or a hard-coded colour of its own; it assembles components.

## Design system

**Colours.** The visual identity is that of the original mock-up and a single
file is authoritative: `netverify/theme.py`. Background `#0a0e14`, panels
`#10161c`, Tunisie Telecom accent `#0072bc`, green `#1e9e6b`, amber `#d97706`,
red `#dc3545`. No new hue has been introduced.

Three defects were fixed without touching that identity:

| Original defect | Fix |
|---|---|
| Two near-identical blues (`#0072bc` / `#1478c8`) for two distinct series | Accent + amber, two tokens already present (ΔE 24.7 under protanopia) |
| Red `#dc3545` (4.02:1) and light blue `#1478c8` (3.94:1) unreadable at small text sizes | Lightened variants for text (`#f47b86`, `#5aa9dc`); original hue kept for marks |
| Green/amber/red map tiers carried by colour alone | Marker shape (circle, diamond, cross) + legend label + value in the tooltip |

The palette was measured on its own surface (`#10161c`): lightness band, chroma
floor, protanopia/deuteranopia separation and contrast — the status trio and the
accent/amber pair pass every check. The map tiers do not (green↔red ΔE 5.6 under
deuteranopia, amber↔red ΔE 14.3 in normal vision): a deliberate choice to keep
the business colour code, compensated by shape and label.

**Charts.** Round-ended bars separated by a 2 px gap in the surface colour, 2 px
lines, ringed markers, a plain hairline grid on the value axis only, no dual Y
scale. A legend as soon as there are two series; direct labels stay sparing (end
point, bar tip). Every chart is doubled by an expandable table: no value is
reachable through colour or tooltip alone.

**Typography.** Proportional figures for the large values (KPI tiles),
`tabular-nums` reserved for columns that have to line up vertically.

## Analytical pages

Three pages do not count work orders but describe the data itself. They rely on
`Backend/analytics.py`, where the computation stays in the database
(`percentile_cont`, `width_bucket`, `AVG() OVER`, `corr`): the front receives
series ready to plot, never 20,000 rows to aggregate.

| Page | What it answers | Forms used |
|---|---|---|
| **Performance** | Is the backlog ageing, is the flow degrading, where is the problem concentrated, what should be fixed first? | Stacked columns, 7-day moving average, heat matrix, Pareto |
| **Line quality** | What is the shape of the estate, its dispersion, which lines are physically degraded? | Histogram with threshold, P10–P90 dumbbells, quadrant scatter |
| **Data quality** | Can the indicators of the other pages be believed? | Ranked bars, status feed, control table |

Three reading rules are upheld there:

- **No implicit denominator.** The SNR margin is only populated on copper pairs
  (2 % of the GPON measurements); every rate shows the population actually
  evaluated next to it, and GPON is excluded from the SNR percentiles rather
  than compared on 162 points against 6,000.
- **Ageing starts from the data, not from the clock.** The referential is a
  frozen extract: measured against `now()`, the whole backlog would fall into
  the oldest bucket. The reference date is written under the chart.
- **What is empty is shown as empty.** Five NetScan columns are never populated;
  displaying them at 0 % is the only way of not accidentally building an
  indicator on top of them.

**Colour of the new forms.** The diagnostic scatter plot is coloured by
technology — an identity — and not by severity: severity already reads from the
position of the point against the two thresholds. The triplet used
(`#0072bc`/`#d97706`/`#1e9e6b`) passes the five palette checks, where a
green/amber/red encoding failed on the amber↔red separation in normal vision
(ΔE 14.3). The heat matrix uses a single-hue ramp (`theme.SEQUENTIAL`), capped at
`BRAND_400` so that the value written in the cell keeps 4.5:1 of contrast.

**Logo.** The platform carries the operator's mark, not one of its own: the
Tunisie Telecom drop signs the sign-in screen, the navigation bar and the
banner of the home page, and it is the icon of the browser tab. `assets/` holds
a vector rendering of it, rebuilt from its geometry by `make_brand.py` so that
the project depends on no font and no image editor. **To use the corporate
artwork instead, save it as `assets/tt-logo.png` (lockup) and
`assets/tt-mark.png` (drop alone) and restart** — `netverify/brand.py` prefers
the PNG over the generated SVG, there is nothing else to change.

## Extension points

Adding a page:

1. create `netverify/views/my_page.py` with a `render()` function;
2. export it from `netverify/views/__init__.py`;
3. register it in `SECTIONS` of `dashboard.py` (`st.Page(...)`).

The navigation rail, the breadcrumb and the refresh button follow automatically.

If the page is reserved for supervisors, register it inside the `if supervising:`
branch that builds `SECTIONS` rather than hiding its content at render time: a
page that is never mounted has no URL, so the address does not resolve at all.
The backend must still guard the data — the registry only spares the user a dead
end.

Adding an indicator: instantiate a `Tile` in the view concerned. A change
(`delta`) must only be filled in if the history really exists — the dashboard
never displays a comparison it cannot compute.

## Configuration

| Variable | Role | Default |
|---|---|---|
| `NETVERIFY_API_URL` | Backend as seen from the Streamlit server | `http://127.0.0.1:8000` |
| `NETVERIFY_PUBLIC_API_URL` | Backend as seen from the browser (assistant) | value of `NETVERIFY_API_URL` |
| `NETVERIFY_CACHE_TTL` | Lifetime of the data cache (s) | `60` |

## Authentication

Access is restricted to technicians: `dashboard.py` calls
`auth.require_sign_in()` **before** `st.navigation`, and stops there if the
session is not open. No `st.Page` exists at that point — a view is therefore not
reachable by its URL while bypassing the sign-in screen.

```
dashboard.py
  └── auth.require_sign_in()      sign-in screen, or True
        └── api.sign_in()         POST /auth/login → token
              └── st.session_state["nv_token"]
```

`api.get()` carries the token on every call and folds it into the cache key:
Streamlit's cache is shared by the whole server, and a response obtained with
one user's session must not be servable to another. On `401` the session is
purged and the application rerun — the sign-in screen reappears instead of an
error on every card.

The holder's role is displayed permanently in the top bar — accented for a
supervisor — and supervisor actions are disabled with a tooltip rather than
letting the click through only to show a refusal. The server applies the same
rule on its side: the interface is never the only guard.

The registry itself depends on the role, and the two pages that differ are the
two nominative ones. A supervisor gets **Analytics** (which ranks the field
agents by name) and **Audit trail** (which names who triggered what); a
technician gets **My results** in their place — the same figures, but only their
own, with the team present as an anonymous benchmark. Everything else is shared.
`auth.is_supervisor()` is the single gate: it decides both which pages are
mounted and which actions are offered.

Full model, account creation and configuration: see
[`SECURITY.md`](../SECURITY.md) at the root.

## Archive

`_legacy/dashboard_v1.py` keeps the previous version (single file with tabs),
for comparison in the internship report. It is no longer executed.
