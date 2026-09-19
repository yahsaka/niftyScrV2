"""Explicit, bounded Yahoo EOD downloads. Network dependencies are lazy imports."""
from datetime import datetime
import logging
import time
import numpy as np
import pandas as pd
from src.freshness import completed_cutoff
from src.indicators import calculate_indicators

LOGGER = logging.getLogger(__name__)


def clean_prices(frame: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.copy()
        frame.columns = frame.columns.get_level_values(0)
    required = ["Open", "High", "Low", "Close", "Volume"]
    if frame.empty or not set(required).issubset(frame):
        raise ValueError("Missing OHLCV observations.")
    frame = frame.copy()
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_convert("Asia/Kolkata").tz_localize(None)
    frame.index = index.normalize()
    frame = frame.loc[frame.index.date <= completed_cutoff(now)].sort_index()
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"], how="all")
    if frame.empty or frame.index.duplicated().any():
        raise ValueError("No completed sessions, or duplicate session dates.")
    values = frame[required].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(values).all(axis=1) & (values[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
    valid &= (values["Volume"] >= 0) & (values["Low"] <= values[["Open", "Close"]].min(axis=1))
    valid &= (values["High"] >= values[["Open", "Close"]].max(axis=1)) & (values["High"] >= values["Low"])
    if not valid.all():
        raise ValueError(f"Invalid or incomplete OHLCV on {frame.index[~valid][0].date()}.")
    frame[required] = values
    if "Adj Close" not in frame:
        # Never silently substitute raw prices for dividend-adjusted analysis.
        raise ValueError("Provider did not supply Adj Close for the explicit adjustment policy.")
    adjusted = pd.to_numeric(frame["Adj Close"], errors="coerce")
    if not ((adjusted > 0) & np.isfinite(adjusted)).all():
        raise ValueError("Invalid adjusted price history.")
    frame["Adj Close"] = adjusted
    for column in ("Dividends", "Stock Splits"):
        frame[column] = pd.to_numeric(frame.get(column, pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0)
    return frame


def download_batch(symbols: list[str], retries: int = 2) -> tuple[dict, dict]:
    import yfinance as yf
    result, errors = {}, {}
    pending = list(symbols)
    for attempt in range(retries):
        try:
            raw = yf.download(pending, period="3y", interval="1d", auto_adjust=False,
                              back_adjust=False, actions=True, repair=False, group_by="ticker",
                              threads=min(4, len(pending)), progress=False, timeout=20)
        except Exception as exc:
            raw = pd.DataFrame()
            for symbol in pending:
                errors[symbol] = f"Download failed: {type(exc).__name__}"
        for symbol in list(pending):
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    level = next((i for i in range(raw.columns.nlevels) if symbol in raw.columns.get_level_values(i)), None)
                    if level is None:
                        raise ValueError("Symbol absent from provider response.")
                    frame = raw.xs(symbol, axis=1, level=level)
                else:
                    if len(pending) != 1:
                        raise ValueError("Unrecognized multi-symbol provider response.")
                    frame = raw
                result[symbol] = calculate_indicators(clean_prices(frame))
                pending.remove(symbol)
                errors.pop(symbol, None)
            except (ValueError, KeyError, TypeError) as exc:
                errors[symbol] = str(exc)
        if not pending:
            break
        if attempt + 1 < retries:
            time.sleep(2 ** (attempt + 1))
    return result, errors


if __name__ == "__main__":
    from src.pipeline import main
    main()
