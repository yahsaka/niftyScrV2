from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import gzip
import json
import numpy as np
import pandas as pd
import pytest
from src.config import ExecutionConfig, StrategyConfig
from src.data_fetcher import clean_prices
from src.demo import demo_snapshot
from src.freshness import IST, completed_cutoff, freshness, order_window
from src.indicators import calculate_indicators, ema
from src.market import atomic_bytes, coverage, load_snapshot, pack_frame, save_snapshot, screen_snapshot, unpack_frame
from src.pipeline import build_snapshot
from src.portfolio import analyze_holdings
from src.screener import BULLISH, BEARISH, UNKNOWN, evaluate_setup, filter_signals, market_regimes
from ui.charts import calendar_range, index_chart, price_chart


def perfect_frame():
    return pd.DataFrame({"Close": [99., 105.], "EMA_50": [95., 95.], "EMA_200": [100., 100.],
                         "RSI_14": [50., 65.], "Volume": [1000., 5000.], "VOL_SMA_20": [1000., 1000.],
                         "MACD_12_26_9": [-.5, 1.], "MACDs_12_26_9": [0., .5]})


@pytest.mark.parametrize("rsi, passed", [(60, False), (60.001, True), (70, True), (70.001, False)])
def test_rsi_boundaries(rsi, passed):
    frame = perfect_frame()
    frame.loc[1, "RSI_14"] = rsi
    assert evaluate_setup(frame, 1, BULLISH)["checks"]["RSI_60_TO_70"] is passed


@pytest.mark.parametrize("volume, passed", [(2000., False), (2000.001, True)])
def test_volume_boundary_strictly_above_2x(volume, passed):
    frame = perfect_frame()
    frame.loc[1, "Volume"] = volume
    assert evaluate_setup(frame, 1, BULLISH)["checks"]["VOLUME_SPIKE_2X"] is passed


def test_unknown_regime_does_not_classify():
    assert evaluate_setup(perfect_frame(), 1, UNKNOWN) is None


def test_missing_long_term_ema_does_not_score():
    frame = perfect_frame()
    frame.loc[1, "EMA_200"] = np.nan
    assert evaluate_setup(frame, 1, BULLISH) is None


def test_literal_search_square_bracket_is_safe():
    rows = [{"ticker": "INFY", "company": "Infosys", "score": 5, "status": "Trade-Ready", "triggers": []}]
    assert filter_signals(rows, "[") == []
    assert filter_signals(rows, "inFo") == rows


def test_warmup_ema_seed_and_flat_rsi():
    frame = pd.DataFrame({"Open": 100., "High": 101., "Low": 99., "Close": 100., "Adj Close": 100., "Volume": 100.}, index=pd.bdate_range("2020-01-01", periods=230))
    indicators = calculate_indicators(frame)
    assert indicators["EMA_200"].iloc[:199].isna().all()
    assert indicators["EMA_200"].iloc[199] == 100
    assert indicators["RSI_14"].iloc[-1] == 50
    assert indicators["ATR_PRICE"].iloc[-1] == pytest.approx(2)


def test_sma_seeded_ema_golden_values():
    series = pd.Series([1., 2., 3., 4., 5.])
    result = ema(series, 3)
    assert result.iloc[:2].isna().all()
    assert result.iloc[2:].tolist() == [2., 3., 4.]


def test_adjusted_analysis_and_raw_execution_units():
    frame = pd.DataFrame({"Open": 100., "High": 102., "Low": 98., "Close": 100., "Adj Close": 50., "Volume": 100.}, index=pd.bdate_range("2020-01-01", periods=250))
    calculated = calculate_indicators(frame)
    assert calculated["Close"].iloc[-1] == 100
    assert calculated["EMA_200"].iloc[-1] == 50
    assert calculated["ATR_14"].iloc[-1] == pytest.approx(2)
    assert calculated["ATR_PRICE"].iloc[-1] == pytest.approx(4)


def test_regime_warmup_does_not_look_ahead():
    frame = pd.DataFrame({"Close": list(np.linspace(100, 200, 250))}, index=pd.bdate_range("2020-01-01", periods=250))
    regimes = market_regimes(frame)
    assert list(regimes.values())[:201] == [UNKNOWN] * 201
    assert list(regimes.values())[-1] == BULLISH
    frame.iloc[-3:] = 1
    assert list(market_regimes(frame).values())[-1] == BEARISH


def test_calendar_ranges_are_not_row_counts():
    frame = pd.DataFrame({"Close": 100}, index=pd.bdate_range("2025-01-01", "2025-09-05"))
    cropped = calendar_range(frame, "3M")
    assert cropped.index[0] >= pd.Timestamp("2025-06-05")
    assert len(cropped) < 90


def test_friday_data_current_before_monday_eod_but_order_window_closes():
    now = datetime(2025, 1, 6, 12, tzinfo=IST)
    assert freshness("2025-01-03", now)["is_fresh"]
    assert order_window("2025-01-03", now)[0] is False


def test_after_cutoff_rejects_yesterday_as_fresh():
    now = datetime(2025, 1, 6, 16, 20, tzinfo=IST)
    assert completed_cutoff(now).isoformat() == "2025-01-06"
    assert not freshness("2025-01-03", now)["is_fresh"]


def test_future_missing_and_invalid_dates_are_not_fresh():
    now = datetime(2025, 1, 6, 17, tzinfo=IST)
    for value in (None, "broken", "2025-01-07"):
        assert not freshness(value, now)["is_fresh"]


def test_intraday_bar_is_discarded(bars):
    now = datetime(2025, 1, 3, 12, tzinfo=IST)
    result = clean_prices(bars.head(3), now)
    assert result.index[-1] == pd.Timestamp("2025-01-02")


def test_invalid_ohlcv_is_rejected(bars):
    bars.loc[bars.index[2], "Low"] = 200
    with pytest.raises(ValueError, match="Invalid"):
        clean_prices(bars)


def test_snapshot_roundtrip_and_all_screen_views_use_same_id(tmp_path, registry):
    snapshot = demo_snapshot(registry)
    path = tmp_path / "snapshot.gz"
    save_snapshot(snapshot, path)
    reloaded = load_snapshot(path)
    assert reloaded == snapshot
    assert screen_snapshot(reloaded) == screen_snapshot(snapshot)
    assert coverage(snapshot)["analyzed"] == 12


def test_corrupt_snapshot_never_silently_becomes_current(tmp_path):
    path = tmp_path / "bad.gz"
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="damaged"):
        load_snapshot(path)
    assert path.read_bytes() == b"corrupt"


def test_atomic_write_preserves_previous_file_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_bytes(b"original")
    monkeypatch.setattr("src.market.os.replace", lambda *args: (_ for _ in ()).throw(OSError("simulated")))
    with pytest.raises(OSError):
        atomic_bytes(path, b"replacement")
    assert path.read_bytes() == b"original"
    assert not list(tmp_path.glob(".tmp-*"))


def test_unpriced_portfolio_is_not_healthy(registry):
    holding = {"ticker": "INFY", "quantity": 10, "average_price": 100, "industry": "IT"}
    report = analyze_holdings([holding], {"stocks": {}, "as_of": "2025-01-02"})
    assert report["unpriced"] == report["unassessed"] == 1
    assert report["price_coverage_pct"] == report["analysis_coverage_pct"] == 0
    assert report["rows"][0]["value"] is None


def test_portfolio_pnl_uses_only_comparable_priced_cost(registry):
    snapshot = demo_snapshot(registry)
    priced_close = unpack_frame(snapshot["stocks"]["INFY"])["Close"].iloc[-1]
    holdings = [{"ticker": "INFY", "quantity": 10, "average_price": 100, "industry": "IT"},
                {"ticker": "MISSING", "quantity": 10, "average_price": 100, "industry": "Other"}]
    report = analyze_holdings(holdings, snapshot)
    assert report["price_coverage_pct"] == 50
    assert report["priced_pnl"] == pytest.approx(10 * priced_close - 1000)


def test_stale_instrument_never_enters_current_shortlist(registry):
    snapshot = demo_snapshot(registry)
    snapshot["stocks"]["INFY"]["quality"] = "Stale"
    assert all(row["ticker"] != "INFY" for row in screen_snapshot(snapshot))


def test_pipeline_scans_explicit_members_not_previous_cache(registry):
    snapshot = demo_snapshot(registry)
    small = deepcopy(registry)
    small.universe = ["INFY", "TCS"]
    def downloader(symbols):
        output = {}
        for symbol in symbols:
            if symbol == "^NSEI":
                output[symbol] = unpack_frame(snapshot["index"])
            else:
                output[symbol] = unpack_frame(snapshot["stocks"][symbol.removesuffix(".NS")])
        return output, {}
    result = build_snapshot(small, snapshot, downloader=downloader)
    assert set(result["stocks"]) == {"INFY", "TCS"}
    assert result["universe_size"] == 2
    assert coverage(result)["analyzed"] == 2


def test_failed_provider_response_does_not_count_as_current(registry):
    snapshot = demo_snapshot(registry)
    small = deepcopy(registry)
    small.universe = ["INFY"]
    def downloader(symbols):
        if symbols == ["^NSEI"]:
            return {"^NSEI": unpack_frame(snapshot["index"])}, {}
        return {}, {"INFY.NS": "simulated network failure"}
    result = build_snapshot(small, snapshot, downloader=downloader)
    assert coverage(result)["analyzed"] == 0
    assert result["stocks"]["INFY"]["quality"] == "Refresh failed"
    assert screen_snapshot(result) == []


def test_benchmark_failure_does_not_produce_new_snapshot(registry):
    with pytest.raises(ValueError, match="Benchmark refresh failed"):
        build_snapshot(registry, downloader=lambda symbols: ({}, {"^NSEI": "test failure"}))


def test_plotly_objects_validate_with_both_palettes(registry):
    snapshot = demo_snapshot(registry)
    for dark in (False, True):
        assert index_chart(unpack_frame(snapshot["index"]), dark).to_json()
        assert price_chart(unpack_frame(snapshot["stocks"]["INFY"]), dark).to_json()


@pytest.mark.parametrize("kwargs", [{"hold_sessions": 0}, {"atr_multiplier": float('nan')}, {"round_trip_cost_bps": -1}, {"entry_slippage_bps": 2000}])
def test_execution_configuration_validation(kwargs):
    with pytest.raises(ValueError):
        ExecutionConfig(**kwargs)


def test_threshold_ordering_validation():
    with pytest.raises(ValueError):
        StrategyConfig(watchlist_min_score=6, qualified_min_score=3)
