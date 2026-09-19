from pathlib import Path

from ui.visuals import metric_card, money, status_strip


def test_money_uses_indian_digit_grouping():
    assert money(100000) == "₹1,00,000"
    assert money(1234567.5, 2) == "₹12,34,567.50"


def test_status_strip_displays_refresh_in_ist():
    html = status_strip({
        "as_of": "2026-09-18",
        "generated_at": "2026-09-19T02:21:00+00:00",
        "is_demo": False,
    })
    assert "19 Sep · 07:51 IST" in html
    assert "UTC" not in html


def test_metric_cards_only_show_icons_when_semantically_requested():
    plain = metric_card("Account equity", "₹1,00,000")
    explicit = metric_card("Qualified setups", "3", symbol="scan")
    assert "nq-card-icon" not in plain
    assert "nq-card-icon" in explicit


def test_css_loads_roboto_and_has_active_contrast_overrides():
    css = Path("assets/theme.css").read_text()
    assert "fonts.googleapis.com" in css
    assert 'font-family:"Roboto"' in css
    assert 'button[aria-pressed="true"] *' in css
    assert 'stBaseButton-primaryFormSubmit' in css


def test_ui_source_regressions_are_patched():
    app = Path("app.py").read_text()
    portfolio = Path("ui/screens/portfolio.py").read_text()
    backtest = Path("ui/screens/backtest.py").read_text()
    settings = Path("ui/screens/settings.py").read_text()
    assert 'st.container(key="navigation-shell")' in app
    assert '"weight_pct", "label": "Cost weight", "format": "pct"' in portfolio
    assert 'page_heading("Backtest"' in backtest
    assert "html(status_strip(ctx.snapshot))" in settings
