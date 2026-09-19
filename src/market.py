"""A single compressed, versioned market snapshot for signals, charts and risk."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from src.config import DEFAULT_STRATEGY
from src.screener import evaluate_setup, UNKNOWN

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "data/market_snapshot.json.gz"
COLUMNS = ["Open", "High", "Low", "Close", "Volume", "Adj Close", "Dividends", "Stock Splits",
           "EMA_50", "EMA_200", "RSI_14", "VOL_SMA_20", "MACD_12_26_9", "MACDs_12_26_9", "ATR_PRICE", "RegimeEMA"]


def empty_snapshot() -> dict:
    return {"schema_version": 2, "snapshot_id": "empty", "as_of": None, "generated_at": None,
            "provider": "Yahoo Finance / yfinance", "market_regime": UNKNOWN,
            "universe_size": 0, "universe": [], "stocks": {}, "index": {"columns": [], "rows": []},
            "regimes": {}, "failures": [], "is_demo": False}


def pack_frame(frame: pd.DataFrame, sessions: int = 520) -> dict:
    columns = [column for column in COLUMNS if column in frame]
    cropped = frame[columns].tail(sessions).replace([np.inf, -np.inf], np.nan)
    # Decimal precision is presentation/storage precision, not currency rounding
    # at each execution step. Six decimals keep the snapshot compact.
    rows = [[str(pd.Timestamp(idx).date())] + [round(float(x), 6) if pd.notna(x) else None for x in row]
            for idx, row in cropped.iterrows()]
    return {"columns": ["Date", *columns], "rows": rows}


def unpack_frame(data: dict) -> pd.DataFrame:
    if not data.get("rows"):
        return pd.DataFrame()
    frame = pd.DataFrame(data["rows"], columns=data["columns"])
    frame["Date"] = pd.to_datetime(frame["Date"], errors="raise")
    frame = frame.set_index("Date").sort_index()
    if frame.index.duplicated().any():
        raise ValueError("Duplicate market sessions in snapshot.")
    for column in frame:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["AnalysisClose"] = frame.get("Adj Close", frame["Close"])
    if "MACD_12_26_9" in frame and "MACDs_12_26_9" in frame:
        frame["MACDh_12_26_9"] = frame["MACD_12_26_9"] - frame["MACDs_12_26_9"]
    return frame


def atomic_bytes(path: Path, content: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_snapshot(snapshot: dict, path: Path = SNAPSHOT_PATH) -> None:
    content = json.dumps(snapshot, separators=(",", ":"), allow_nan=False).encode()
    atomic_bytes(Path(path), gzip.compress(content, compresslevel=6, mtime=0))


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict:
    if not Path(path).exists():
        return empty_snapshot()
    try:
        with gzip.open(path, "rt", encoding="utf-8") as file:
            snapshot = json.load(file)
        if snapshot.get("schema_version") != 2 or not isinstance(snapshot.get("stocks"), dict):
            raise ValueError("Unsupported market snapshot schema.")
        return snapshot
    except (OSError, ValueError, EOFError) as exc:
        raise ValueError("The market snapshot is damaged. Rerun the market workflow; the file was not reset.") from exc


def snapshot_hash(snapshot: dict) -> str:
    content = {key: snapshot[key] for key in ("stocks", "index", "as_of", "regimes")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, allow_nan=False).encode()).hexdigest()[:16]


def screen_snapshot(snapshot: dict, config=DEFAULT_STRATEGY) -> list[dict]:
    signals = []
    for ticker in snapshot.get("universe", []):
        stock = snapshot.get("stocks", {}).get(ticker)
        if not stock or stock.get("quality") != "Current" or stock.get("data_as_of") != snapshot.get("as_of"):
            continue
        frame = unpack_frame(stock)
        if frame.empty:
            continue
        setup = evaluate_setup(frame, len(frame) - 1, snapshot.get("market_regime", UNKNOWN), ticker, config)
        if setup and setup["score"] >= config.watchlist_min_score:
            signals.append({**setup, "company": stock.get("company", ticker), "industry": stock.get("industry", "Unknown")})
    return sorted(signals, key=lambda row: (-row["score"], -(row.get("volume_ratio") or 0), row["ticker"]))


def coverage(snapshot: dict) -> dict:
    universe = snapshot.get("universe", [])
    stocks = snapshot.get("stocks", {})
    current = sum(stocks.get(symbol, {}).get("quality") == "Current" for symbol in universe)
    dated = sum(stocks.get(symbol, {}).get("data_as_of") == snapshot.get("as_of") for symbol in universe) if snapshot.get("as_of") else 0
    return {"universe": len(universe), "analyzed": current, "dated": dated,
            "unassessed": len(universe) - current, "percent": current / len(universe) * 100 if universe else 0}
