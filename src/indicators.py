"""Transparent pandas indicators; no optional TA binary changes the definitions.

EMA: first-window SMA seed, then adjust=False EMA (pandas-ta's non-TA-Lib
convention). RSI/ATR: exponentially weighted Wilder smoothing, adjust=True,
with a 14-observation warm-up. Flat RSI is explicitly 50; zero losses gives 100.
Analysis uses the provider's Adj Close / Close adjustment factor. OHLC columns
remain in provider execution units; ATR_PRICE converts signal ATR back to them.
"""
import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").astype(float).copy()
    out = pd.Series(np.nan, index=series.index, dtype=float)
    valid = values.first_valid_index()
    if valid is None:
        return out
    start = values.index.get_loc(valid)
    end = start + length
    if end > len(values) or values.iloc[start:end].isna().any():
        return out
    values.iloc[:end - 1] = np.nan
    values.iloc[end - 1] = pd.to_numeric(series.iloc[start:end]).mean()
    return values.ewm(span=length, adjust=False).mean()


def rma(series: pd.Series, length: int = 14) -> pd.Series:
    return series.ewm(alpha=1 / length, min_periods=length, adjust=True).mean()


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    needed = {"Open", "High", "Low", "Close", "Volume"}
    if not needed.issubset(out):
        raise ValueError(f"Missing OHLCV columns: {sorted(needed - set(out))}")
    raw = out["Close"].astype(float)
    adjusted = out.get("Adj Close", raw).astype(float)
    factor = adjusted / raw.replace(0, np.nan)
    close = adjusted
    high, low = out["High"] * factor, out["Low"] * factor
    out["AnalysisClose"] = close
    out["EMA_50"] = ema(close, 50)
    out["EMA_200"] = ema(close, 200)
    delta = close.diff()
    gain = rma(delta.clip(lower=0))
    loss = rma(-delta.clip(upper=0))
    out["RSI_14"] = 100 * gain / (gain + loss)
    out.loc[(gain == 0) & (loss == 0), "RSI_14"] = 50.0
    out["VOL_SMA_20"] = out["Volume"].rolling(20, min_periods=20).mean()
    out["MACD_12_26_9"] = ema(close, 12) - ema(close, 26)
    out["MACDs_12_26_9"] = ema(out["MACD_12_26_9"], 9)
    out["MACDh_12_26_9"] = out["MACD_12_26_9"] - out["MACDs_12_26_9"]
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    out["ATR_14"] = rma(tr)
    out["ATR_PRICE"] = out["ATR_14"] / factor
    return out
