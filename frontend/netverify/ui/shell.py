"""Application shell: theme, floating navigation bar, cards, sections."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Mapping, Sequence

import streamlit as st

from .. import theme
from ..brand import LOCKUP, logo
from ..settings import ORG_NAME
from ..utils import esc
from .icons import icon


def inject_theme() -> None:
    """Injects the stylesheet and arms the Plotly template, on every run."""
    theme.register_plotly_template()
    st.html(theme.full_css())


# ══════════════════════════════════════════════════════════════════════════════
# Floating navigation bar
# ══════════════════════════════════════════════════════════════════════════════

# The bar carries the operator's mark without its wordmark: at 34 px the
# "Tunisie Telecom" inside the drop would be unreadable, and the line right
# next to it already says it.
_BRAND = f"""
<div class="brand">
  {logo("brand-mark")}
  <div>
    <div class="brand-name">Net<span>Verify</span></div>
    <div class="brand-sub">{ORG_NAME.upper()}</div>
  </div>
</div>
"""


def nav_key(page) -> str:
    """Stable widget key of a navigation chip."""
    return f"nav_{getattr(page, 'url_path', '') or 'home'}"


def _nav_chip(page) -> None:
    if st.button(page.title, icon=page.icon or None, key=nav_key(page)):
        st.switch_page(page)


def render_topnav(sections: Mapping[str, Sequence], current) -> None:
    """The original floating bar: brand, navigation tabs, session identity.

    Difference with v1: the chips actually navigate. They used to be purely
    decorative and doubled by a row of tabs just below.

    They are `st.button` + `st.switch_page`, and not `st.page_link`: the link
    navigates through a browser-side JavaScript handler, impossible to cover
    with tests, whereas the button goes through the standard
    widget -> rerun circuit, which is verified automatically (see the simulated
    click on each chip in the tests).
    """
    pages = [page for group in sections.values() for page in group]

    with st.container(key="nvtopnav"):
        brand, tabs, status = st.columns([2.1, 7.3, 1.8], vertical_alignment="center")

        with brand:
            st.html(_BRAND)

        with tabs:
            with st.container(
                key="nvchips", horizontal=True, horizontal_alignment="center", gap="small"
            ):
                for page in pages:
                    active = getattr(page, "url_path", None) == getattr(current, "url_path", None)
                    if active:
                        with st.container(key="nvactivechip"):
                            _nav_chip(page)
                    else:
                        _nav_chip(page)

        with status:
            with st.container(
                horizontal=True, horizontal_alignment="right", vertical_alignment="center"
            ):
                _user_pill()
                if st.button("", icon=":material/logout:", key="nv_logout",
                             help="Sign out"):
                    from .. import auth

                    auth.end_session()
                    st.rerun()


def _user_pill() -> None:
    """Identity of the session holder, at the right end of the bar.

    `auth` is imported on the fly: it pulls in the whole API layer, which the
    shell itself does not need, and a module-level import would drag it in as
    soon as anything touches the design system.
    """
    from .. import auth

    profile = auth.profile()
    if not profile:
        return

    name = profile.get("full_name") or profile.get("login") or "—"
    label = auth.role_label()
    initials = "".join(word[0] for word in str(name).split()[:2]).upper() or "?"

    # The role is not decoration: it is the reason a page is absent from the bar
    # and a button refuses to be pressed. A supervisor gets the accented variant
    # so the difference is legible at a glance — including on a screenshot.
    tone = " sup" if auth.is_supervisor() else ""

    st.html(
        f"""
        <div class="user-pill" title="{esc(name)} · {esc(label)}">
          <span class="user-avatar">{esc(initials)}</span>
          <span class="user-meta">
            <span class="user-name">{esc(name)}</span>
            <span class="user-role{tone}">{esc(label)}</span>
          </span>
        </div>
        """
    )


# ══════════════════════════════════════════════════════════════════════════════
# Headers
# ══════════════════════════════════════════════════════════════════════════════

def hero(title: str, subtitle: str, badges: Sequence[str] = ()) -> None:
    """Welcome banner of the main page."""
    meta = f'<div class="hero-meta">{"".join(badges)}</div>' if badges else ""
    st.html(
        f"""
        <div class="hero">
          <div>
            {logo("hero-logo", LOCKUP)}
            <h1>{esc(title)}</h1>
            <p>{esc(subtitle)}</p>
            {meta}
          </div>
        </div>
        """
    )


def render_page_header(title: str, subtitle: str, icon_name: str = "grid") -> None:
    st.html(
        f"""
        <div class="pagehead">
          <div class="pagehead-icon">{icon(icon_name, 22)}</div>
          <div>
            <h1>{esc(title)}</h1>
            <p>{esc(subtitle)}</p>
          </div>
        </div>
        """
    )


# ══════════════════════════════════════════════════════════════════════════════
# Cards & sections
# ══════════════════════════════════════════════════════════════════════════════

@contextmanager
def card(key: str, height: int | str | None = None):
    """"Card" container of the design system.

    `key` must be unique within the page; the `nvcard-` prefix triggers the
    style. The native border is requested on top of the stylesheet: if a future
    version of Streamlit renamed the `st-key-*` class, the cards would stay
    framed with the colours of `.streamlit/config.toml`.
    """
    kwargs = {"key": f"nvcard-{key}", "border": True}
    if height is not None:
        kwargs["height"] = height
    with st.container(**kwargs) as container:
        yield container


def section(title: str, subtitle: str = "", aside: str = "", accent: str = "accent") -> None:
    """Original panel title (coloured `||` bar), enriched with a subtitle."""
    sub = f'<div class="panel-sub">{esc(subtitle)}</div>' if subtitle else ""
    side = f'<div class="panel-aside">{esc(aside)}</div>' if aside else ""
    st.html(
        f"""
        <div class="panel-head">
          <div>
            <div class="panel-title"><span class="{accent}">||</span>{esc(title)}</div>
            {sub}
          </div>
          {side}
        </div>
        """
    )


def legend(entries: Iterable[tuple[str, str, str]], note: str = "") -> None:
    """Manual legend. `entries` = (colour, label, shape: dot|bar|diamond|cross)."""
    items = []
    for color, label, shape in entries:
        if shape == "bar":
            mark = f'<span style="width:12px;height:4px;border-radius:2px;background:{color}"></span>'
        elif shape == "diamond":
            mark = (
                f'<span style="width:9px;height:9px;background:{color};'
                'transform:rotate(45deg);border-radius:1px"></span>'
            )
        elif shape == "cross":
            mark = f'<span style="color:{color};font-weight:800;font-size:12px;line-height:1">✕</span>'
        else:
            mark = f'<span style="width:9px;height:9px;border-radius:50%;background:{color}"></span>'
        items.append(
            f'<span class="legend-item"><span class="legend-mark">{mark}</span>{esc(label)}</span>'
        )
    tail = f'<span class="legend-note">{esc(note)}</span>' if note else ""
    st.html(f'<div class="legend">{"".join(items)}{tail}</div>')


def key_values(pairs: Sequence[tuple[str, str]]) -> None:
    """Key/value grid for the detail sheets."""
    cells = "".join(
        f'<div><div class="kv-key">{esc(k)}</div><div class="kv-val">{esc(v)}</div></div>'
        for k, v in pairs
    )
    st.html(f'<div class="kv">{cells}</div>')


def spacer(height: int = 14) -> None:
    st.html(f'<div style="height:{height}px"></div>')


def caption(text: str) -> None:
    st.html(f'<div class="legend-note" style="margin-top:18px">{esc(text)}</div>')


__all__ = [
    "card", "caption", "hero", "inject_theme", "key_values", "legend",
    "render_page_header", "render_topnav", "section", "spacer",
]
