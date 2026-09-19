"""Non-overlapping per-ticker event study, not a pooled portfolio backtest."""
from dataclasses import asdict, replace
from datetime import datetime, time
import math
import pandas as pd
from src.config import DEFAULT_EXECUTION, DEFAULT_STRATEGY, ExecutionConfig
from src.execution import ExecutionError, create_order, new_ledger, process_ledger
from src.freshness import IST
from src.indicators import calculate_indicators
from src.screener import UNKNOWN, evaluate_setup


def simulate_trade(frame: pd.DataFrame, signal_idx: int, atr: float,
                   config: ExecutionConfig = DEFAULT_EXECUTION, ticker="TEST",
                   expected_sessions=None) -> dict | None:
    if signal_idx + 1 >= len(frame):
        return None
    work = frame.copy()
    if not isinstance(work.index, pd.DatetimeIndex):
        work.index = pd.bdate_range("2020-01-01", periods=len(work))
    signal_date = str(work.index[signal_idx].date())
    setup = {"ticker": ticker, "last_date": signal_date, "close": float(work["Close"].iloc[signal_idx]),
             "atr_at_signal": float(atr), "score": 6}
    ledger = create_order(new_ledger(), setup, 100_000.0, 2.0, config,
                          requested_at=datetime.combine(work.index[signal_idx].date(), time(16, 30), IST), source="backtest")
    ledger = process_ledger(ledger, {ticker: work}, str(work.index[-1].date()), expected_sessions)
    return ledger["trades"][0]


def _execute_trade(df, signal_idx, atr, config=DEFAULT_EXECUTION):
    """Compatibility adapter for original tests/consumers, with explicit fee fields."""
    trade = simulate_trade(df, signal_idx, atr, config)
    if not trade or trade["status"] != "CLOSED":
        return None
    return {"Entry Price": trade["entry_price"], "Stop Price": trade["stop_price"],
            "Exit Price": trade["exit_price"], "Entry Fee": trade["entry_fee"], "Exit Fee": trade["exit_fee"],
            "Return": trade["realized_pnl_pct"] / 100, "Exit Reason": trade["exit_reason"],
            "Exit Date": pd.Timestamp(trade["exit_date"]), "Hit_SL": trade["exit_reason"].startswith("ATR stop")}


def summarize(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0, "win_rate": None, "mean_return_pct": None, "median_return_pct": None,
                "profit_factor": None, "mean_benchmark_pct": None}
    returns = pd.Series([t["realized_pnl_pct"] for t in trades], dtype=float)
    wins, losses = returns[returns > 0].sum(), -returns[returns < 0].sum()
    benchmarks = [t["benchmark_return_pct"] for t in trades if t.get("benchmark_return_pct") is not None]
    return {"trades": len(trades), "win_rate": float((returns > 0).mean() * 100),
            "mean_return_pct": float(returns.mean()), "median_return_pct": float(returns.median()),
            "profit_factor": float(wins / losses) if losses else None,
            "mean_benchmark_pct": float(pd.Series(benchmarks).mean()) if benchmarks else None}


def run_event_study(frames: dict[str, pd.DataFrame], regimes: dict, start: str, end: str,
                    strategy=DEFAULT_STRATEGY, execution=DEFAULT_EXECUTION,
                    min_score: int | None = None, benchmark: pd.DataFrame | None = None) -> dict:
    threshold = strategy.qualified_min_score if min_score is None else min_score
    if not 0 <= threshold <= 6 or start > end:
        raise ValueError("Invalid study dates or minimum score.")
    trades, skipped, errors = [], {"unfinished": 0, "corporate_action": 0, "unfundable": 0}, []
    benchmark = benchmark if benchmark is not None else pd.DataFrame()
    expected = list(benchmark.index.strftime("%Y-%m-%d")) if not benchmark.empty else None
    for ticker, source in frames.items():
        if source.empty:
            errors.append({"ticker": ticker, "reason": "No observations"})
            continue
        prepared = source if "EMA_200" in source else calculate_indicators(source)
        prepared = prepared.loc[prepared.index <= end]
        occupied_until = None
        for idx in range(1, len(prepared)):
            session = str(prepared.index[idx].date())
            if session < start or occupied_until and session < occupied_until:
                continue
            regime = regimes.get(session, regimes.get(prepared.index[idx].date(), UNKNOWN))
            setup = evaluate_setup(prepared, idx, regime, ticker, strategy)
            if not setup or setup["score"] < threshold:
                continue
            atr = setup.get("atr_at_signal")
            if atr is None or not math.isfinite(atr) or atr <= 0:
                continue
            try:
                trade = simulate_trade(prepared, idx, atr, execution, ticker, expected)
            except ExecutionError as exc:
                errors.append({"ticker": ticker, "signal_date": session, "reason": str(exc)})
                break
            except ValueError:
                skipped["unfundable"] += 1
                continue
            if not trade or trade["status"] in {"OPEN", "PENDING"}:
                skipped["unfinished"] += 1
                break
            if trade["status"] == "REVIEW_REQUIRED" or (trade["status"] == "CANCELLED" and "Corporate" in trade.get("cancel_reason", "")):
                skipped["corporate_action"] += 1
                # The account is not reconciled; do not keep trading through the
                # action in this ticker's study under inconsistent price units.
                break
            if trade["status"] != "CLOSED":
                skipped["unfundable"] += 1
                continue
            trade["score"] = setup["score"]
            trade["triggers"] = setup["triggers"]
            trade["benchmark_return_pct"] = None
            entry_day, exit_day = pd.Timestamp(trade["entry_date"]), pd.Timestamp(trade["exit_date"])
            if entry_day in benchmark.index and exit_day in benchmark.index:
                entry = float(benchmark.loc[entry_day, "Open"])
                exit_price = float(benchmark.loc[exit_day, "Close"])
                if entry > 0 and math.isfinite(exit_price):
                    trade["benchmark_return_pct"] = (exit_price / entry - 1) * 100
            trades.append(trade)
            occupied_until = trade["exit_date"]
    trades.sort(key=lambda t: (t["signal_date"], t["ticker"]))
    # Descriptive holdout split; no parameter optimization or claim of edge.
    midpoint = pd.Timestamp(start) + (pd.Timestamp(end) - pd.Timestamp(start)) * .7
    early = [t for t in trades if pd.Timestamp(t["signal_date"]) < midpoint]
    late = [t for t in trades if pd.Timestamp(t["signal_date"]) >= midpoint]
    return {"kind": "per_ticker_event_study", "strategy": asdict(strategy), "execution": asdict(execution),
            "min_score": threshold, "start": start, "end": end, "tickers": list(frames),
            "summary": summarize(trades), "trades": trades, "skipped": skipped, "errors": errors,
            "chronological_split": {"split_date": str(midpoint.date()), "earlier": summarize(early), "later": summarize(late)},
            "limitations": ["Current constituent universe, not point-in-time membership; survivorship bias applies.",
                            "No same-ticker overlaps; cross-ticker samples can overlap and independently reuse the notional budget.",
                            "Not a pooled portfolio return, forecast, or probability of profit.",
                            "Provider OHLC may reflect historical split revisions; affected positions are excluded/frozen.",
                            "Benchmark uses matching next-open to exit-close dates, without fees or dividend reinvestment.",
                            "Daily bars do not model liquidity, partial fills or intraday paths."]}


def cost_sensitivity(frames, regimes, start, end, strategy, execution, benchmark, min_score=None):
    results = []
    for multiplier in (0.0, 1.0, 2.0):
        config = replace(execution, round_trip_cost_bps=execution.round_trip_cost_bps * multiplier)
        report = run_event_study(frames, regimes, start, end, strategy, config, min_score, benchmark)
        results.append({"cost_bps": config.round_trip_cost_bps, **report["summary"]})
    return results
