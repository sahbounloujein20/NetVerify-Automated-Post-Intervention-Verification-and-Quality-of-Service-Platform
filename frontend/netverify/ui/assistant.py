"""Floating conversational assistant (embedded HTML widget)."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from ..settings import API_URL

# The widget runs in the browser: it needs a URL reachable from the client
# machine, which is not necessarily the one the Streamlit server sees (the case
# of a containerised deployment).
PUBLIC_API_URL = os.getenv("NETVERIFY_PUBLIC_API_URL", API_URL).rstrip("/")

TEMPLATE = Path(__file__).resolve().parents[2] / "chatbot.html"


@st.cache_data(show_spinner=False)
def _markup(path: str, api_url: str, token: str) -> str | None:
    try:
        template = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    return template.replace("__API_URL__", api_url).replace("__TOKEN__", token)


def render() -> None:
    """Mounts the assistant. Called once, outside the pages, so it stays visible everywhere.

    Since `/chatbot/query` is now authenticated, the session token is copied
    into the template: the widget runs in the browser and does not share the
    Streamlit state, so it cannot read it any other way. The token therefore
    ends up in the iframe's DOM — the accepted trade-off of a client-side call,
    bounded by the length of the shift and by the iframe sandbox.
    """
    from .. import auth

    if not auth.is_signed_in():
        return

    markup = _markup(str(TEMPLATE), PUBLIC_API_URL, auth.token())
    if markup is None:
        return

    # The widget repositions itself with `position: fixed` from inside its own
    # iframe; the box reserved here is only an anchor point.
    if hasattr(st, "iframe"):
        st.iframe(markup, height=96, width=96)
    else:  # Streamlit < 1.53
        import streamlit.components.v1 as components

        components.html(markup, height=96, width=96, scrolling=False)
