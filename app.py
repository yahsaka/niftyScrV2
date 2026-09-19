"""Nifty Quant Screener — personal, no-cost, end-of-day research workspace."""
from pathlib import Path
import os
from dotenv import load_dotenv
import streamlit as st
from src.config import StrategyConfig
from src.instruments import InstrumentRegistry
from src.market import SNAPSHOT_PATH, empty_snapshot, load_snapshot, screen_snapshot
from src.storage import LocalStore, SessionStore
from ui.context import Context
from ui.theme import apply_theme
from ui.visuals import brand
from ui.widgets import html

load_dotenv()
st.set_page_config(page_title="Nifty Quant Screener", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")


@st.cache_data(show_spinner=False)
def cached_registry():
    return InstrumentRegistry.load()


@st.cache_data(show_spinner=False)
def cached_snapshot(path: str, modified_ns: int, size: int):
    return load_snapshot(Path(path))


@st.cache_data(show_spinner=False, max_entries=12)
def cached_signals(snapshot_id: str, strategy: dict, _snapshot: dict):
    # Only public market observations are globally cached, never a portfolio.
    return screen_snapshot(_snapshot, StrategyConfig(**strategy))


@st.cache_data(show_spinner=False)
def cached_demo():
    from src.demo import demo_snapshot
    return demo_snapshot(cached_registry())


def main():
    if "demo-mode" not in st.session_state:
        st.session_state["demo-mode"] = os.getenv("NIFTY_DEMO", "0") == "1"
    demo = st.session_state["demo-mode"]
    if st.session_state.get("active-data-mode") != demo:
        st.session_state["active-data-mode"] = demo
        st.session_state.pop("current-study", None)
        st.session_state.pop("selected_ticker", None)
    try:
        if demo:
            store = SessionStore(st.session_state, key="demo_workspace")
        else:
            mode = os.getenv("NIFTY_STORAGE", "session").lower()
            if mode not in {"session", "local"}:
                raise ValueError("NIFTY_STORAGE must be session or local.")
            store = LocalStore() if mode == "local" else SessionStore(st.session_state)
        workspace = store.load()
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        st.info("The existing workspace was not reset. Restore a verified backup to a new trusted local database, or return to session mode. See docs/STORAGE_AND_PRIVACY.md.")
        return
    if "_pending_theme" in st.session_state:
        st.session_state["dark-mode"] = st.session_state.pop("_pending_theme")
    if "dark-mode" not in st.session_state:
        st.session_state["dark-mode"] = workspace["preferences"].get("dark_mode", False)
    dark = st.session_state["dark-mode"]
    apply_theme(dark)
    def save_theme():
        try:
            latest = store.load()
            latest["preferences"]["dark_mode"] = st.session_state["dark-mode"]
            store.save(latest)
        except ValueError as exc:
            st.warning(str(exc))
    with st.container(key="topbar"):
        left, middle, right = st.columns([4.2, 3, 1.4], vertical_alignment="center")
        with left:
            html(brand())
        with middle:
            html('<div class="nq-top-meta"><span class="nq-dot"></span>PERSONAL WORKSPACE &nbsp; / &nbsp; NSE · END OF DAY</div>')
        with right:
            st.toggle("Dark mode", key="dark-mode", on_change=save_theme)
    screens = ["Overview", "Screener", "Portfolio", "Paper trading", "Backtest", "Settings"]
    if "_pending_route" in st.session_state:
        route = st.session_state.pop("_pending_route")
        if route in screens:
            st.session_state["navigation"] = route
    if "navigation" not in st.session_state:
        route = st.query_params.get("page", "Overview")
        st.session_state["navigation"] = route if route in screens else "Overview"
    with st.container(key="navigation"):
        route = st.segmented_control("Workspace navigation", screens, key="navigation", label_visibility="collapsed", width="stretch") or "Overview"
    st.query_params["page"] = route
    if demo:
        st.warning("SYNTHETIC PREVIEW · Fixture prices are not market observations. This is an isolated demo workspace; personal trade/import actions are disabled. Return via Settings → Data & refresh.")
    try:
        if demo:
            snapshot = cached_demo()
        elif "market-override" in st.session_state:
            snapshot = st.session_state["market-override"]
        elif SNAPSHOT_PATH.exists():
            stat = SNAPSHOT_PATH.stat()
            snapshot = cached_snapshot(str(SNAPSHOT_PATH), stat.st_mtime_ns, stat.st_size)
        else:
            snapshot = empty_snapshot()
        registry = cached_registry()
        signals = cached_signals(snapshot["snapshot_id"], workspace["strategy"], snapshot)
    except (ValueError, OSError, KeyError) as exc:
        st.error(str(exc))
        snapshot, registry, signals = empty_snapshot(), cached_registry(), []
    ctx = Context(workspace, store, snapshot, registry, signals, dark)
    # Routed screens: hidden screens do not run imports, price downloads or studies.
    from ui.screens import overview, screener, portfolio, paper, backtest, settings
    routes = {"Overview": overview.render, "Screener": screener.render, "Portfolio": portfolio.render,
              "Paper trading": paper.render, "Backtest": backtest.render, "Settings": settings.render}
    try:
        routes[route](ctx)
    except (ValueError, KeyError, OSError) as exc:
        st.error(f"This action could not be completed: {exc}")
        st.caption("No fallback result was fabricated. Review data quality/settings and retry.")
    html('<div class="nq-footer"><span>Nifty Quant Screener &nbsp; / &nbsp; Research, not recommendations.</span><span>End-of-day observations · Cash-only simulation · Backup personal changes</span></div>')


if __name__ == "__main__":
    main()
