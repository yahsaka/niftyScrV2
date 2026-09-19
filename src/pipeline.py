"""Build one consistent market snapshot. Never reads or writes personal ledgers."""
from datetime import datetime, timezone
import argparse
import json
import logging
from pathlib import Path
from src.data_fetcher import download_batch
from src.instruments import InstrumentRegistry, provider_symbol
from src.market import (ROOT, SNAPSHOT_PATH, atomic_bytes, coverage, empty_snapshot, load_snapshot,
                        pack_frame, save_snapshot, screen_snapshot, snapshot_hash)
from src.screener import market_regimes

LOGGER = logging.getLogger(__name__)


def build_snapshot(registry: InstrumentRegistry, previous: dict | None = None, progress=None,
                   batch_size: int = 20, sessions: int = 520, downloader=download_batch) -> dict:
    if not 220 <= sessions <= 760:
        raise ValueError("Snapshot must retain between 220 and 760 sessions.")
    previous = previous or empty_snapshot()
    index_data, index_errors = downloader(["^NSEI"])
    if "^NSEI" not in index_data:
        raise ValueError(f"Benchmark refresh failed. Previous snapshot retained. {index_errors.get('^NSEI', '')}")
    index = index_data["^NSEI"]
    if len(index) < 203:
        raise ValueError("Nifty 50 has insufficient history. Previous snapshot retained.")
    as_of = str(index.index[-1].date())
    if previous.get("as_of") and as_of < previous["as_of"]:
        raise ValueError("Provider benchmark moved backwards. Previous snapshot retained.")
    regimes = market_regimes(index)
    index = index.copy()
    index["RegimeEMA"] = index["Adj Close"].ewm(span=200, adjust=False, min_periods=200).mean()
    snapshot = {**empty_snapshot(), "as_of": as_of, "generated_at": datetime.now(timezone.utc).isoformat(),
                "universe": registry.universe, "universe_size": len(registry.universe),
                "index": pack_frame(index, sessions), "regimes": regimes,
                "market_regime": regimes.get(as_of, "Unknown"), "history_sessions": sessions,
                "universe_source": "Bundled, user-controlled Nifty 500 constituent list",
                "price_policy": "Adj Close ratio for indicators; auto_adjust=False provider OHLC for execution; action guards enabled."}
    for offset in range(0, len(registry.universe), batch_size):
        batch = registry.universe[offset:offset + batch_size]
        frames, failures = downloader([provider_symbol(symbol) for symbol in batch])
        for symbol in batch:
            meta = registry.records[symbol]
            frame = frames.get(provider_symbol(symbol))
            if frame is None:
                reason = failures.get(provider_symbol(symbol), "No provider response.")
                old = previous.get("stocks", {}).get(symbol, {})
                snapshot["stocks"][symbol] = {**old, **meta, "quality": "Refresh failed", "error": reason}
                snapshot["failures"].append({"ticker": symbol, "reason": reason})
                continue
            frame = frame.loc[frame.index <= as_of]
            if frame.empty:
                snapshot["stocks"][symbol] = {**meta, "quality": "Missing", "error": "No bar at or before the benchmark date."}
                snapshot["failures"].append({"ticker": symbol, "reason": "No usable completed bars"})
                continue
            date = str(frame.index[-1].date())
            warm = len(frame) >= 201 and frame["EMA_200"].iloc[-1] == frame["EMA_200"].iloc[-1]
            quality = "Stale" if date != as_of else "Current" if warm else "Insufficient history"
            snapshot["stocks"][symbol] = {**meta, **pack_frame(frame, sessions), "quality": quality, "data_as_of": date}
        if progress:
            progress(min(offset + len(batch), len(registry.universe)), len(registry.universe))
    snapshot["snapshot_id"] = snapshot_hash(snapshot)
    snapshot["coverage"] = coverage(snapshot)
    old_qualified = {row["ticker"] for row in screen_snapshot(previous) if row["status"] == "Trade-Ready"}
    qualified = {row["ticker"] for row in screen_snapshot(snapshot) if row["status"] == "Trade-Ready"}
    snapshot["new_qualified"] = sorted(qualified - old_qualified) if previous.get("as_of") else []
    snapshot["comparison_as_of"] = previous.get("as_of")
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=520)
    parser.add_argument("--output", type=Path, default=SNAPSHOT_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    status_path = ROOT / "data/pipeline_status.json"
    status = {"attempted_at": datetime.now(timezone.utc).isoformat()}
    try:
        registry = InstrumentRegistry.load()
        previous = load_snapshot(args.output)
        snapshot = build_snapshot(registry, previous, lambda done, total: LOGGER.info("%s / %s instruments", done, total), sessions=args.sessions)
        save_snapshot(snapshot, args.output)
        summary = {key: snapshot[key] for key in ("as_of", "generated_at", "snapshot_id", "market_regime", "coverage", "failures")}
        summary["signals"] = screen_snapshot(snapshot)
        atomic_bytes(ROOT / "data/latest_screener_results.json", json.dumps(summary, indent=2, allow_nan=False).encode())
        status.update(success=True, coverage=snapshot["coverage"], failed_count=len(snapshot["failures"]))
        LOGGER.info("Snapshot saved: %s; coverage %s", args.output, snapshot["coverage"])
    except Exception as exc:
        status.update(success=False, error=str(exc))
        LOGGER.exception("Market refresh failed; existing market snapshot was not replaced.")
        raise
    finally:
        atomic_bytes(status_path, json.dumps(status, indent=2).encode())


if __name__ == "__main__":
    main()
