"""
HTTP client towards the FastAPI backend.

Every read returns a `Result`: "the backend answered an empty list" is
explicitly distinguished from "the backend is unreachable". The views can
therefore show a calm empty state rather than a false alarm (and vice versa).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests
import streamlit as st

from .settings import (
    API_URL,
    CACHE_TTL,
    HEALTH_TTL,
    TIMEOUT_HEALTH,
    TIMEOUT_READ,
    TIMEOUT_WRITE,
)


@dataclass(frozen=True)
class Result:
    """Response of a read call."""

    data: Any
    ok: bool
    error: str | None = None
    # Service absent or switched off: the call executed nothing at all, so a
    # fallback carries no risk. To be distinguished from a failure that happened
    # *during* the processing, which is never replayed.
    unreachable: bool = False

    @property
    def failed(self) -> bool:
        return not self.ok

    @property
    def empty(self) -> bool:
        return self.ok and not self.data

    def list(self) -> list[dict]:
        return self.data if isinstance(self.data, list) else []

    def dict(self) -> dict:
        return self.data if isinstance(self.data, dict) else {}


# Sentinel values of the "no filter" option in the selectors.
NO_FILTER_VALUES = (None, "", "All")


def endpoint(path: str, **params: Any) -> str:
    """Builds an API path with the query parameters filtered."""
    clean = {k: v for k, v in params.items() if v not in NO_FILTER_VALUES}
    return f"{path}?{urlencode(clean)}" if clean else path


def _token() -> str:
    """Token of the current session, read straight from the Streamlit state.

    We do not go through `netverify.auth`: that module already imports `api`,
    and a cross-import would be circular. The key is the only shared thing.
    """
    return st.session_state.get("nv_token", "")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


# The token is part of the cache key. Two reasons: a response obtained with one
# user's session must not be served to another — Streamlit's cache is shared by
# the whole server, not per tab — and signing out mechanically invalidates the
# corresponding entries.
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _fetch(path: str, token: str) -> tuple[Any, bool, str | None, bool]:
    try:
        response = requests.get(
            f"{API_URL}{path}", headers=_headers(token), timeout=TIMEOUT_READ
        )
        response.raise_for_status()
        return response.json(), True, None, False
    except requests.exceptions.ConnectionError:
        return None, False, "Backend unreachable", False
    except requests.exceptions.Timeout:
        return None, False, f"Timed out ({TIMEOUT_READ}s)", False
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        if code == 401:
            return None, False, "Session expired", True
        if code == 403:
            return None, False, "Access denied for this role", False
        if code == 429:
            return None, False, "Too many requests — try again in a moment", False
        return None, False, f"HTTP error {code}", False
    except ValueError:
        return None, False, "Unreadable response (invalid JSON)", False
    except Exception as exc:  # pragma: no cover - safety net
        return None, False, str(exc), False


def get(path: str, **params: Any) -> Result:
    """Cached read of an endpoint, authenticated by the session token."""
    data, ok, error, expired = _fetch(endpoint(path, **params), _token())

    if expired:
        # The token has expired or the account has been deactivated. The session
        # is cut immediately and the app reruns: letting the page draw would
        # show an error on every card instead of the sign-in screen.
        _fetch.clear()
        health.clear()
        st.session_state.pop("nv_token", None)
        st.session_state.pop("nv_profile", None)
        st.session_state["nv_session_expired"] = True
        st.rerun()

    return Result(data=data, ok=ok, error=error)


def sign_in(login: str, password: str) -> Result:
    """Exchanges the credentials for a token. Never cached."""
    try:
        response = requests.post(
            f"{API_URL}/auth/login",
            json={"login": login, "password": password},
            timeout=TIMEOUT_WRITE,
        )
        response.raise_for_status()
        return Result(data=response.json(), ok=True)
    except requests.exceptions.ConnectionError:
        return Result(data=None, ok=False, error="Backend unreachable", unreachable=True)
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        if code == 429:
            return Result(data=None, ok=False,
                          error="Too many attempts. Wait a minute before trying again.")
        detail = None
        if exc.response is not None:
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = None
        return Result(data=None, ok=False, error=detail or "Sign-in failed.")
    except Exception as exc:
        return Result(data=None, ok=False, error=str(exc))


def post(path: str, payload: dict | None = None) -> Result:
    """Write (not cached) — clears the read cache on success."""
    try:
        response = requests.post(
            f"{API_URL}{path}", json=payload,
            headers=_headers(_token()), timeout=TIMEOUT_WRITE,
        )
        response.raise_for_status()
        _fetch.clear()
        return Result(data=response.json(), ok=True)
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        if code == 403:
            return Result(
                data=None, ok=False,
                error="Action restricted to supervisors — your account does not have that role.",
            )
        if code == 429:
            return Result(data=None, ok=False,
                          error="Too many triggers. Try again later.")
        detail = None
        if exc.response is not None:
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = exc.response.text[:200]
        return Result(data=None, ok=False, error=detail or str(exc))
    except Exception as exc:
        return Result(data=None, ok=False, error=str(exc))


def post_url(url: str, payload: dict | None = None, timeout: int = TIMEOUT_WRITE) -> Result:
    """Write to an absolute URL (n8n webhook) — same contract as `post`."""
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        _fetch.clear()
        return Result(data=response.json(), ok=True)
    except requests.exceptions.ConnectionError:
        return Result(data=None, ok=False, error="Service unreachable", unreachable=True)
    except requests.exceptions.Timeout:
        return Result(data=None, ok=False, error=f"Timed out ({timeout}s)")
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        # 404 = n8n answers but the workflow is not active: nothing has run.
        if code == 404:
            return Result(data=None, ok=False, error="n8n workflow inactive", unreachable=True)
        return Result(data=None, ok=False, error=f"HTTP error {code or '?'}")
    except ValueError:
        return Result(data=None, ok=False, error="Unreadable response (invalid JSON)")
    except Exception as exc:  # pragma: no cover - safety net
        return Result(data=None, ok=False, error=str(exc))


@st.cache_data(ttl=HEALTH_TTL, show_spinner=False)
def health() -> bool:
    """Is the backend answering? (result kept 10 s so it is not hammered)"""
    try:
        return requests.get(f"{API_URL}/", timeout=TIMEOUT_HEALTH).status_code == 200
    except Exception:
        return False


def refresh() -> None:
    """Invalidates every data cache."""
    _fetch.clear()
    health.clear()
