"""Deterministic, explicitly synthetic UI fixtures. Never used by the pipeline."""
import numpy as np
import pandas as pd
from src.indicators import calculate_indicators
from src.market import empty_snapshot, pack_frame, snapshot_hash, coverage
from src.screener import market_regimes


def demo_snapshot(registry):
    rng = np.random.default_rng(20260919)
    dates = pd.bdate_range(end="2025-09-05", periods=760)
    def prices(close, volumes):
        opens = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, .002, len(close)))
        high = np.maximum(opens, close) * (1 + rng.uniform(.004, .016, len(close)))
        low = np.minimum(opens, close) * (1 - rng.uniform(.004, .016, len(close)))
        return pd.DataFrame({"Open": opens, "High": high, "Low": low, "Close": close, "Adj Close": close,
                             "Volume": volumes, "Dividends": 0.0, "Stock Splits": 0.0}, index=dates)
    index_close = 16000 + np.arange(len(dates)) * 10 + np.sin(np.arange(len(dates)) / 24) * 700 + rng.normal(0, 65, len(dates))
    index = calculate_indicators(prices(index_close, rng.integers(10_000, 200_000, len(dates))))
    index["RegimeEMA"] = index["Close"].ewm(span=200, adjust=False, min_periods=200).mean()
    tickers = [ticker for ticker in ["INFY", "TCS", "RELIANCE", "HDFCBANK", "ICICIBANK", "LT", "SBIN", "ITC", "TITAN", "AXISBANK", "MARUTI", "SUNPHARMA"] if ticker in registry.records]
    snapshot = {**empty_snapshot(), "as_of": "2025-09-05", "generated_at": "2025-09-05T11:30:00+00:00",
                "market_regime": "Bullish", "regimes": market_regimes(index), "index": pack_frame(index),
                "universe": tickers, "universe_size": len(tickers), "history_sessions": 520, "is_demo": True,
                "provider": "SYNTHETIC FIXTURES — NOT MARKET DATA"}
    for i, ticker in enumerate(tickers):
        base = 420 + i * 185
        close = base * (1 + .035 * np.sin(np.arange(len(dates)) / 14) + rng.normal(0, .004, len(dates)))
        if i < 4:
            close[-45:] = base * np.linspace(1.05, .97, 45)
            close[-1] = base * 1.065
        else:
            close[-60:] = base * (np.linspace(.96, 1.07, 60) + .009 * np.sin(np.arange(60) * 1.7))
        volumes = rng.integers(100_000, 300_000, len(dates)).astype(float)
        volumes[-1] = 900_000 if i < 8 else 250_000
        frame = calculate_indicators(prices(close, volumes))
        snapshot["stocks"][ticker] = {**registry.records[ticker], **pack_frame(frame), "quality": "Current", "data_as_of": snapshot["as_of"]}
    snapshot["coverage"] = coverage(snapshot)
    snapshot["snapshot_id"] = "demo-" + snapshot_hash(snapshot)
    return snapshot
