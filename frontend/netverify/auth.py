"""
Dashboard user session: sign-in screen, token, sign-out.

Since the platform is open to technicians only, no page is drawn before
`require_sign_in()`. The gate is unique and placed in `dashboard.py`, before
the navigation: a view cannot therefore be reached by its URL while bypassing
the sign-in screen, because nothing is mounted until the session is open.

The token lives in `st.session_state`, that is to say on the Streamlit server
side, and is never written into the URL nor into browser storage. Closing the
tab is enough to lose the session.
"""

from __future__ import annotations

import streamlit as st

from . import api
from .brand import LOCKUP, logo
from .settings import APP_NAME, APP_TAGLINE, ORG_NAME
from .utils import esc

KEY_TOKEN = "nv_token"
KEY_PROFILE = "nv_profile"
KEY_EXPIRED = "nv_session_expired"


# ══════════════════════════════════════════════════════════════════════════════
# Session state
# ══════════════════════════════════════════════════════════════════════════════

def token() -> str:
    return st.session_state.get(KEY_TOKEN, "")


def profile() -> dict:
    return st.session_state.get(KEY_PROFILE, {}) or {}


def is_signed_in() -> bool:
    return bool(token())


def role() -> str:
    """Canonical role of the session.

    The backend normalises it to its English form before putting it in the
    token; the legacy French values are still mapped here, for a session opened
    just before that normalisation was deployed.
    """
    raw = str(profile().get("role", "")).strip().lower()
    return {"technicien": "technician", "superviseur": "supervisor"}.get(raw, raw)


# What the operator reads in the top bar. `service` is a non-human account, so
# it is named for what it is rather than by its technical role.
ROLE_LABELS = {
    "supervisor": "Supervisor",
    "technician": "Technician",
    "service": "Automaton",
}


def role_label() -> str:
    return ROLE_LABELS.get(role(), role().capitalize() or "—")


def is_supervisor() -> bool:
    """True for the roles that see the estate, and the people in it.

    The single gate of the interface: it decides both which pages are mounted
    and which actions are offered. The backend enforces the same rule on its
    own — this only spares the user a refusal they could not have foreseen.
    """
    return role() in ("supervisor", "service")


def end_session(expired: bool = False) -> None:
    """Clears the session and empties the data caches.

    Clearing the cache is not cosmetic: `api` memoises the responses per token,
    and leaving those entries behind would keep business data in the server's
    memory after the user has left.
    """
    for key in (KEY_TOKEN, KEY_PROFILE):
        st.session_state.pop(key, None)
    st.session_state[KEY_EXPIRED] = expired
    api.refresh()


# ══════════════════════════════════════════════════════════════════════════════
# Sign-in screen
# ══════════════════════════════════════════════════════════════════════════════

def require_sign_in() -> bool:
    """Shows the sign-in screen if needed. `True` when the session is open."""
    if is_signed_in():
        return True

    _sign_in_screen()
    return False


def _sign_in_screen() -> None:
    _, centre, _ = st.columns([1, 1.15, 1])

    with centre:
        st.html(
            f"""
            <div class="login-head">
              {logo("login-logo", LOCKUP)}
              <h1>{esc(APP_NAME)}</h1>
              <p>{esc(APP_TAGLINE)}</p>
              <div class="login-org">{esc(ORG_NAME.upper())}</div>
            </div>
            """
        )

        if st.session_state.pop(KEY_EXPIRED, False):
            st.warning("Session expired — please sign in again.", icon=":material/schedule:")

        with st.form("nv_sign_in", border=True):
            st.markdown("#### Sign in")
            login = st.text_input(
                "Login", key="nv_login", autocomplete="username"
            )
            password = st.text_input(
                "Password", type="password", key="nv_password",
                autocomplete="current-password",
            )
            submitted = st.form_submit_button(
                "Sign in", icon=":material/login:", width="stretch", type="primary"
            )

        if submitted:
            _attempt_sign_in(login, password)

        st.html(
            '<div class="login-note">Access restricted to Tunisie Telecom technicians '
            'and supervisors.</div>'
        )


def _attempt_sign_in(login: str, password: str) -> None:
    if not login or not password:
        st.error("Enter your login and your password.", icon=":material/error:")
        return

    response = api.sign_in(login, password)
    if response.failed:
        # The backend already returns a message that does not distinguish
        # "unknown account" from "wrong password": it is reused as is rather
        # than replaced by a more talkative one.
        st.error(response.error or "Sign-in failed.", icon=":material/error:")
        return

    data = response.dict()
    st.session_state[KEY_TOKEN] = data.get("access_token", "")
    st.session_state[KEY_PROFILE] = {
        "login": data.get("login", login),
        "full_name": data.get("full_name", ""),
        "role": data.get("role", ""),
    }
    api.refresh()
    st.rerun()
