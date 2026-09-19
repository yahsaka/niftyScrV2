"""Actual Streamlit AppTest tests; skipped only when Streamlit is not installed.

No fake Streamlit module or dependency placeholders are used. CI installs the
pinned runtime and executes these tests in Python 3.12.
"""
import pytest
st = pytest.importorskip("streamlit", reason="Real Streamlit runtime is required; domain tests do not substitute it.")
from streamlit.testing.v1 import AppTest


@pytest.mark.app
@pytest.mark.parametrize("page", ["Overview", "Screener", "Portfolio", "Paper trading", "Backtest", "Settings"])
def test_empty_application_screens(page, monkeypatch):
    monkeypatch.setenv("NIFTY_STORAGE", "session")
    monkeypatch.setenv("NIFTY_DEMO", "0")
    app = AppTest.from_file("app.py", default_timeout=30)
    app.session_state["navigation"] = page
    app.run()
    assert not app.exception
    assert not any("This action could not be completed" in item.value for item in app.error)


@pytest.mark.app
@pytest.mark.parametrize("page", ["Overview", "Screener", "Portfolio", "Paper trading", "Backtest", "Settings"])
def test_synthetic_application_screens(page, monkeypatch):
    monkeypatch.setenv("NIFTY_STORAGE", "session")
    monkeypatch.setenv("NIFTY_DEMO", "1")
    app = AppTest.from_file("app.py", default_timeout=30)
    app.session_state["navigation"] = page
    app.run()
    assert not app.exception
    assert not any("This action could not be completed" in item.value for item in app.error)


@pytest.mark.app
@pytest.mark.parametrize("dark", [False, True])
def test_theme_toggle_and_stock_detail(dark, monkeypatch):
    monkeypatch.setenv("NIFTY_DEMO", "1")
    app = AppTest.from_file("app.py", default_timeout=30)
    app.session_state["navigation"] = "Screener"
    app.session_state["dark-mode"] = dark
    app.session_state["active-data-mode"] = True
    app.session_state["selected_ticker"] = "INFY"
    app.run()
    assert not app.exception
    assert not any("This action could not be completed" in item.value for item in app.error)
    assert len(app.get("plotly_chart")) == 2


@pytest.mark.app
def test_settings_sections(monkeypatch):
    monkeypatch.setenv("NIFTY_DEMO", "0")
    for section in ("Workspace", "Data & refresh", "Model settings", "Learn"):
        app = AppTest.from_file("app.py", default_timeout=30)
        app.session_state["navigation"] = "Settings"
        app.session_state["settings-section"] = section
        app.run()
        assert not app.exception
        assert not any("This action could not be completed" in item.value for item in app.error)
