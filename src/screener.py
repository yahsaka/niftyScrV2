"""The original six rules, shared by live screening and historical research."""
import math
import pandas as pd
from src.config import DEFAULT_STRATEGY, StrategyConfig
from src.indicators import calculate_indicators

BULLISH, BEARISH, UNKNOWN = "Bullish", "Bearish", "Unknown"
WATCHLIST_MIN_SCORE = DEFAULT_STRATEGY.watchlist_min_score
TRADE_READY_MIN_SCORE = DEFAULT_STRATEGY.qualified_min_score
MAX_PCT_ABOVE_50EMA = DEFAULT_STRATEGY.max_pct_above_50ema
RULES = {
    "ABOVE_EMA_200": ("Above 200 EMA", "Adjusted close is above the 200-session EMA."),
    "EMA_200_BREAKOUT": ("Fresh 200 EMA breakout", "Previous close was at or below its EMA; current close is above."),
    "ABOVE_EMA_50": ("Above 50 EMA", "Adjusted close is above the 50-session EMA."),
    "VOLUME_SPIKE_2X": ("Volume above 2×", "Volume strictly exceeds twice the 20-session mean (including today)."),
    "RSI_60_TO_70": ("RSI in the 60–70 band", "RSI is strictly above 60 and no higher than 70."),
    "MACD_BULLISH_CROSS": ("Fresh MACD crossover", "MACD (12,26,9) crossed above its signal on this session."),
}


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def market_regimes(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty or "Close" not in frame:
        return {}
    close = frame.get("Adj Close", frame["Close"])
    # Preserve the original market filter's adjust=False EWM definition, but
    # with a genuine 200-observation warm-up and three valid comparisons.
    ema200 = close.ewm(span=200, adjust=False, min_periods=200).mean()
    valid = close.notna() & ema200.notna()
    below = (close < ema200).where(valid)
    output = {}
    for idx, dt in enumerate(frame.index):
        window = below.iloc[max(0, idx - 2):idx + 1]
        output[str(pd.Timestamp(dt).date())] = (
            UNKNOWN if len(window) < 3 or window.isna().any()
            else BEARISH if bool(window.all()) else BULLISH
        )
    return output


def evaluate_setup(df: pd.DataFrame, idx: int, market_regime: str, ticker: str = "",
                   config: StrategyConfig = DEFAULT_STRATEGY) -> dict | None:
    if idx < 1 or idx >= len(df) or market_regime != BULLISH:
        return None
    current, previous = df.iloc[idx], df.iloc[idx - 1]
    close = finite(current.get("AnalysisClose", current.get("Close")))
    prev_close = finite(previous.get("AnalysisClose", previous.get("Close")))
    e50, e200 = finite(current.get("EMA_50")), finite(current.get("EMA_200"))
    pe200 = finite(previous.get("EMA_200"))
    if any(value is None or value <= 0 for value in (close, prev_close, e50, e200)):
        return None
    extension = close / e50 - 1
    if extension > config.max_pct_above_50ema + 1e-12:
        return None
    volume, average = finite(current.get("Volume")), finite(current.get("VOL_SMA_20"))
    rsi = finite(current.get("RSI_14"))
    m, s = finite(current.get("MACD_12_26_9")), finite(current.get("MACDs_12_26_9"))
    pm, ps = finite(previous.get("MACD_12_26_9")), finite(previous.get("MACDs_12_26_9"))
    checks = {
        "ABOVE_EMA_200": close > e200,
        "EMA_200_BREAKOUT": pe200 is not None and close > e200 and prev_close <= pe200,
        "ABOVE_EMA_50": close > e50,
        "VOLUME_SPIKE_2X": volume is not None and average is not None and average > 0 and volume > 2 * average,
        "RSI_60_TO_70": rsi is not None and 60 < rsi <= 70,
        "MACD_BULLISH_CROSS": None not in (m, s, pm, ps) and m > s and pm <= ps,
    }
    triggers = [name for name, passed in checks.items() if passed]
    score = len(triggers)
    # Internal status retained for compatibility; presentation says Qualified.
    status = "Trade-Ready" if score >= config.qualified_min_score else "Watchlist" if score >= config.watchlist_min_score else "No setup"
    timestamp = current.name
    date = str(timestamp.date() if hasattr(timestamp, "date") else timestamp)
    return {"ticker": ticker, "last_date": date, "close": finite(current.get("Close")),
            "analysis_close": close, "atr_at_signal": finite(current.get("ATR_PRICE", current.get("ATR_14"))),
            "rsi_14": rsi, "pct_above_50": extension * 100,
            "volume_ratio": volume / average if volume is not None and average and average > 0 else None,
            "score": score, "status": status, "checks": checks, "triggers": triggers,
            "triggers_str": ", ".join(triggers), "strategy_version": config.version}


def evaluate_signals(ticker, df, market_regime, config=DEFAULT_STRATEGY):
    if len(df) < 201:
        return None
    prepared = df if "EMA_200" in df else calculate_indicators(df)
    result = evaluate_setup(prepared, len(prepared) - 1, market_regime, ticker, config)
    return result if result and result["score"] >= config.watchlist_min_score else None


def filter_signals(signals: list[dict], query="", statuses=None, min_score=0, industries=None, triggers=None) -> list[dict]:
    """Literal substring search, stable order and a genuine empty result."""
    query = query.strip().casefold()
    return [row for row in signals
            if (not query or query in f"{row['ticker']} {row.get('company', '')}".casefold())
            and (not statuses or row["status"] in statuses)
            and row["score"] >= min_score
            and (not industries or row.get("industry") in industries)
            and (not triggers or set(triggers).issubset(row["triggers"]))]


if __name__ == "__main__":
    from src.pipeline import main
    main()
