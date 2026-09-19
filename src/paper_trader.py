"""Personal paper simulation service. No GitHub Actions ingestion of private data."""
from src.execution import process_ledger
from src.market import unpack_frame


def process_snapshot(ledger: dict, snapshot: dict) -> dict:
    if snapshot.get("is_demo"):
        raise ValueError("Synthetic preview data cannot process the personal account.")
    if not snapshot.get("as_of"):
        raise ValueError("Refresh a market snapshot before processing.")
    tickers = {trade["ticker"] for trade in ledger["trades"] if trade["status"] in {"PENDING", "OPEN", "REVIEW_REQUIRED"}}
    frames = {}
    for ticker in tickers:
        stock = snapshot.get("stocks", {}).get(ticker, {})
        if stock.get("quality") != "Current":
            raise ValueError(f"{ticker}: market data is not current in this snapshot. Account processing is paused.")
        frames[ticker] = unpack_frame(stock)
    sessions = list(unpack_frame(snapshot["index"]).index.strftime("%Y-%m-%d"))
    return process_ledger(ledger, frames, snapshot["as_of"], sessions)


if __name__ == "__main__":
    import os
    from src.market import load_snapshot
    from src.storage import LocalStore
    if os.getenv("NIFTY_STORAGE", "session") != "local":
        raise SystemExit("This local worker requires NIFTY_STORAGE=local. GitHub never processes private ledgers.")
    store = LocalStore()
    workspace = store.load()
    workspace["ledger"] = process_snapshot(workspace["ledger"], load_snapshot())
    store.save(workspace)
    print("Personal ledger processed. Export a backup from Settings.")
