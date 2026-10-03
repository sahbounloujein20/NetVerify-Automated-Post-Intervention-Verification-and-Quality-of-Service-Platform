"""
netverify — front-end layer of the NetVerify dashboard (Tunisie Telecom).

Layout:
    settings.py   configuration (API URL, cache TTL, business thresholds)
    theme.py      design tokens + stylesheet + Plotly template
    brand.py      the Tunisie Telecom mark, inlined into the headers
    api.py        typed HTTP client towards the FastAPI backend
    utils.py      formatting (numbers, dates, rates)
    ui/           component library (shell, cards, charts, tables)
    views/        one business page per module
"""

__version__ = "2.0.0"
