"""Non-nominal states: backend offline, data absent, call error.

v1 showed an undifferentiated `st.info("No data")` — there was no way to
know whether the database was empty or the API was not answering. The three
cases are now distinguished and named.
"""

from __future__ import annotations

import streamlit as st

from ..api import Result
from ..settings import API_URL
from ..utils import esc
from .icons import icon


def offline_banner() -> None:
    """Global banner shown when the backend does not answer."""
    st.html(
        f"""
        <div class="banner">
          <div style="color:var(--red-text);flex:0 0 auto;margin-top:1px">{icon('alert', 18)}</div>
          <div>
            <div class="banner-title">Backend unreachable</div>
            <div class="banner-text">
              No data can be loaded from <code>{esc(API_URL)}</code>.
              Start the API with <code>python -m uvicorn main:app --reload</code>
              in the <code>Backend</code> folder, then reload the page.
            </div>
          </div>
        </div>
        """
    )


def empty_state(
    title: str = "No data",
    message: str = "No record matches the selected filters.",
    icon_name: str = "inbox",
) -> None:
    st.html(
        f"""
        <div class="empty">
          <div class="empty-icon">{icon(icon_name, 21)}</div>
          <h4>{esc(title)}</h4>
          <p>{esc(message)}</p>
        </div>
        """
    )


def error_state(result: Result, what: str = "this data") -> None:
    """Error state of an API call — names the exact cause."""
    st.html(
        f"""
        <div class="empty" style="border-color:rgba(220,53,69,.3)">
          <div class="empty-icon" style="color:var(--red-text)">{icon('alert', 21)}</div>
          <h4>Could not load</h4>
          <p>{esc(result.error or 'Unknown error')} — unable to retrieve {esc(what)}.</p>
        </div>
        """
    )


def guard(result: Result, what: str = "this data", **empty_kwargs) -> bool:
    """Shows the appropriate state and returns True when the data is usable.

    Usage:
        if not states.guard(result, "the work orders"):
            return
    """
    if result.failed:
        error_state(result, what)
        return False
    if result.empty:
        empty_state(**empty_kwargs)
        return False
    return True
