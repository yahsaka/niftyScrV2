"""Shared, deterministic long-only cash execution for paper and backtest paths.

The engine consumes completed daily bars only. Entries are next-session open,
entry-day stops are checked, gap stops fill at the weaker open, and holding
sessions are inclusive. Data gaps/revisions are not silently bridged.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, time
import hashlib
import json
import math
import pandas as pd
from src.config import DEFAULT_EXECUTION, DEFAULT_STRATEGY, ExecutionConfig
from src.freshness import IST
from src.instruments import canonical_symbol

ACTIVE = {"PENDING", "OPEN"}
ALL_STATUSES = ACTIVE | {"CLOSED", "CANCELLED", "REVIEW_REQUIRED"}


class ExecutionError(ValueError):
    """No trustworthy execution can be inferred from the supplied observations."""


def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number.")
    return float(value)


def new_ledger(initial_cash: float = 100_000.0) -> dict:
    return {"schema_version": 2, "currency": "INR", "initial_cash": positive(initial_cash, "Initial cash"),
            "trades": [], "equity_history": []}


def cash_balance(ledger: dict, as_of: str | None = None) -> float:
    cash = ledger["initial_cash"]
    for trade in ledger["trades"]:
        if trade.get("entry_date") and (as_of is None or trade["entry_date"] <= as_of):
            cash -= trade["quantity"] * trade["entry_price"] + trade["entry_fee"]
        if trade.get("exit_date") and (as_of is None or trade["exit_date"] <= as_of):
            cash += trade["quantity"] * trade["exit_price"] - trade["exit_fee"]
        cash += sum(event["amount"] for event in trade.get("dividends", []) if as_of is None or event["date"] <= as_of)
    return float(cash)


def available_cash(ledger: dict) -> float:
    return cash_balance(ledger) - sum(t["allocation"] for t in ledger["trades"] if t["status"] == "PENDING")


def size_position(allocation: float, risk_pct: float, reference_open: float, atr: float,
                  config: ExecutionConfig = DEFAULT_EXECUTION) -> dict:
    positive(allocation, "Allocation")
    positive(reference_open, "Reference open")
    positive(atr, "ATR")
    if not math.isfinite(risk_pct) or not 0 < risk_pct <= 10:
        raise ValueError("Risk budget must be greater than 0 and no more than 10% of allocation.")
    entry = reference_open * (1 + config.entry_slippage_bps / 10_000)
    stop = entry - config.atr_multiplier * atr
    if stop <= 0:
        raise ValueError("ATR stop is non-positive. This setup cannot be sized.")
    cost_per_share = entry * (1 + config.fee_rate)
    modeled_stop_proceeds = stop * (1 - config.exit_slippage_bps / 10_000) * (1 - config.fee_rate)
    risk_per_share = cost_per_share - modeled_stop_proceeds
    risk_budget = allocation * risk_pct / 100
    quantity = max(0, min(math.floor(allocation / cost_per_share), math.floor(risk_budget / risk_per_share)))
    return {"quantity": quantity, "entry_price": entry, "stop_price": stop,
            "entry_fee": quantity * entry * config.fee_rate,
            "cash_required": quantity * cost_per_share, "planned_risk": quantity * risk_per_share,
            "risk_budget": risk_budget}


def create_order(ledger: dict, setup: dict, allocation: float, risk_pct: float,
                 config: ExecutionConfig = DEFAULT_EXECUTION, strategy=DEFAULT_STRATEGY,
                 requested_at: datetime | None = None, source="manual") -> dict:
    """Create a canonical pending order. Caller enforces market freshness/window.

    The engine independently prevents filling a session whose opening time had
    passed when the order was requested. Backtests pass an explicit historical
    EOD timestamp instead of pretending the order was requested today.
    """
    validate_ledger(ledger)
    symbol = canonical_symbol(setup["ticker"])
    signal_date = date.fromisoformat(setup["last_date"]).isoformat()
    if any(t["ticker"] == symbol and t["signal_date"] == signal_date for t in ledger["trades"]):
        raise ValueError("This ticker/session was already staged, cancelled or completed.")
    if any(t["ticker"] == symbol and t["status"] in ACTIVE | {"REVIEW_REQUIRED"} for t in ledger["trades"]):
        raise ValueError("Only one active position per ticker is allowed.")
    if any(t["status"] == "REVIEW_REQUIRED" for t in ledger["trades"]):
        raise ValueError("Resolve the account's data-review warning before staging additional orders.")
    positive(allocation, "Allocation")
    if allocation > available_cash(ledger) + 1e-8:
        raise ValueError("Allocation exceeds unreserved cash. Pending orders reserve their full allocation.")
    if setup.get("score", -1) < strategy.qualified_min_score and source != "backtest":
        raise ValueError("Only qualified setups can be staged for paper execution.")
    atr = positive(setup.get("atr_at_signal"), "Signal ATR")
    reference = positive(setup.get("close"), "Reference close")
    size = size_position(allocation, risk_pct, reference, atr, config)
    if size["quantity"] < 1:
        raise ValueError("Allocation/risk budget cannot fund one share under these assumptions.")
    requested_at = requested_at or datetime.now(IST)
    if requested_at.tzinfo is None:
        raise ValueError("Order creation time must have a timezone.")
    if requested_at.astimezone(IST).date() < date.fromisoformat(signal_date):
        raise ValueError("An order cannot be requested before its signal exists.")
    key = f"{symbol}|{signal_date}"
    trade = {"trade_id": hashlib.sha256(key.encode()).hexdigest()[:20], "ticker": symbol,
             "signal_date": signal_date, "status": "PENDING", "reference_close": reference,
             "atr_at_signal": atr, "allocation": float(allocation), "risk_pct": float(risk_pct),
             "requested_at": requested_at.isoformat(), "strategy_version": strategy.version,
             "strategy": asdict(strategy), "execution": asdict(config), "source": source,
             "sessions_held": 0, "last_processed_session": None, "dividends": [],
             "audit": [{"session": signal_date, "event": "Order staged; next-open simulation, not a market fill."}]}
    out = deepcopy(ledger)
    out["trades"].append(trade)
    return out


def cancel_order(ledger: dict, trade_id: str) -> dict:
    out = deepcopy(ledger)
    trade = next((t for t in out["trades"] if t["trade_id"] == trade_id), None)
    if trade is None or trade["status"] != "PENDING":
        raise ValueError("Only a pending order can be cancelled.")
    trade["status"] = "CANCELLED"
    trade["cancel_reason"] = "Cancelled by owner before processing."
    trade["audit"].append({"session": trade["signal_date"], "event": trade["cancel_reason"]})
    return out


def bar_fingerprint(row: pd.Series) -> str:
    values = [round(float(row.get(key, 0)), 6) for key in ("Open", "High", "Low", "Close", "Dividends", "Stock Splits")]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()[:16]


def _validate_bar(row: pd.Series, session: str):
    for name in ("Open", "High", "Low", "Close"):
        positive(float(row[name]), f"{name} on {session}")
    if row["Low"] > min(row["Open"], row["Close"]) or row["High"] < max(row["Open"], row["Close"]):
        raise ExecutionError(f"Invalid high/low range on {session}.")
    for name in ("Dividends", "Stock Splits"):
        value = float(row.get(name, 0))
        if not math.isfinite(value) or value < 0:
            raise ExecutionError(f"Invalid corporate-action observation on {session}.")


def _review(trade: dict, session: str, reason: str):
    trade["status"] = "REVIEW_REQUIRED"
    trade["review_reason"] = reason
    trade["audit"].append({"session": session, "event": reason})


def _advance_trade(trade: dict, row: pd.Series, session: str, cash_limit: float):
    """Only this function implements fills; both simulation paths call it."""
    cfg = ExecutionConfig(**trade["execution"])
    _validate_bar(row, session)
    split = float(row.get("Stock Splits", 0))
    if split:
        if trade["status"] == "PENDING":
            trade["status"] = "CANCELLED"
            trade["cancel_reason"] = "Corporate action on entry session; adjusted history cannot establish an original-unit fill."
            trade["audit"].append({"session": session, "event": trade["cancel_reason"]})
        else:
            _review(trade, session, "Stock split detected. Position units and historical price basis require reconciliation; performance is unvalued.")
        return
    if trade["status"] == "PENDING":
        requested = datetime.fromisoformat(trade["requested_at"]).astimezone(IST)
        market_open = datetime.combine(date.fromisoformat(session), time(9, 15), IST)
        if requested >= market_open:
            trade["status"] = "CANCELLED"
            trade["cancel_reason"] = "The next session opened before this order was requested. No retrospective fill."
            trade["audit"].append({"session": session, "event": trade["cancel_reason"]})
            return
        try:
            sized = size_position(min(trade["allocation"], cash_limit), trade["risk_pct"], float(row["Open"]), trade["atr_at_signal"], cfg)
        except ValueError as exc:
            sized = {"quantity": 0}
            trade["cancel_reason"] = str(exc)
        if sized["quantity"] < 1:
            trade["status"] = "CANCELLED"
            trade.setdefault("cancel_reason", "Next-open price exceeds cash/risk capacity for one share.")
            trade["audit"].append({"session": session, "event": trade["cancel_reason"]})
            return
        trade.update({key: sized[key] for key in ("quantity", "entry_price", "stop_price", "entry_fee", "planned_risk")})
        trade.update(status="OPEN", entry_date=session)
        trade["audit"].append({"session": session, "event": f"Filled {trade['quantity']} shares at next open with entry slippage and fee."})
    # Existing owners, not new ex-date buyers, receive the modeled dividend.
    dividend = float(row.get("Dividends", 0))
    if dividend and trade["entry_date"] < session:
        trade["dividends"].append({"date": session, "amount": dividend * trade["quantity"]})
        trade["audit"].append({"session": session, "event": "Dividend cash credited; taxes and payment delay not modeled."})
    trade["sessions_held"] += 1
    trade["last_processed_session"] = session
    trade["last_bar_fingerprint"] = bar_fingerprint(row)
    trade["last_mark"] = float(row["Close"])
    raw_exit, reason = None, None
    if float(row["Low"]) <= trade["stop_price"]:
        gap = float(row["Open"]) <= trade["stop_price"]
        raw_exit = float(row["Open"]) if gap else trade["stop_price"]
        reason = "ATR stop (gap)" if gap else "ATR stop"
    elif trade["sessions_held"] >= cfg.hold_sessions:
        raw_exit, reason = float(row["Close"]), "Time exit"
    if raw_exit is not None:
        exit_price = raw_exit * (1 - cfg.exit_slippage_bps / 10_000)
        fee = trade["quantity"] * exit_price * cfg.fee_rate
        basis = trade["quantity"] * trade["entry_price"] + trade["entry_fee"]
        proceeds = trade["quantity"] * exit_price - fee + sum(d["amount"] for d in trade["dividends"])
        trade.update(status="CLOSED", exit_date=session, exit_price=exit_price, exit_fee=fee,
                     exit_reason=reason, realized_pnl=proceeds - basis,
                     realized_pnl_pct=(proceeds / basis - 1) * 100)
        trade["audit"].append({"session": session, "event": f"Closed: {reason}; exit slippage and fee applied."})


def account_summary(ledger: dict, frames: dict[str, pd.DataFrame] | None = None, as_of: str | None = None) -> dict:
    cash = cash_balance(ledger, as_of)
    value, unvalued, unrealized = 0.0, [], 0.0
    for trade in ledger["trades"]:
        if not trade.get("entry_date") or (as_of and trade["entry_date"] > as_of):
            continue
        if trade.get("exit_date") and (as_of is None or trade["exit_date"] <= as_of):
            continue
        frame = (frames or {}).get(trade["ticker"], pd.DataFrame())
        stamp = pd.Timestamp(as_of) if as_of else None
        if trade["status"] == "REVIEW_REQUIRED" or stamp is None or stamp not in frame.index:
            unvalued.append(trade["ticker"])
            continue
        mark = float(frame.loc[stamp, "Close"])
        if not math.isfinite(mark) or mark <= 0:
            unvalued.append(trade["ticker"])
            continue
        marked = trade["quantity"] * mark
        value += marked
        unrealized += marked - (trade["quantity"] * trade["entry_price"] + trade["entry_fee"])
    return {"cash": cash, "available_cash": available_cash(ledger), "positions_value": value,
            "equity": None if unvalued else cash + value, "unvalued": unvalued,
            "unrealized_pnl": None if unvalued else unrealized,
            "realized_pnl": sum(t.get("realized_pnl", 0) for t in ledger["trades"] if t["status"] == "CLOSED"),
            "dividends": sum(d["amount"] for t in ledger["trades"] for d in t.get("dividends", []))}


def process_ledger(ledger: dict, frames: dict[str, pd.DataFrame], as_of: str,
                   expected_sessions: list[str] | None = None) -> dict:
    """Process each session once. Failure before commit leaves the input intact."""
    validate_ledger(ledger)
    date.fromisoformat(as_of)
    out = deepcopy(ledger)
    required = [t for t in out["trades"] if t["status"] in ACTIVE]
    if not required:
        return out
    session_set = set(expected_sessions or [])
    prepared = {}
    for trade in required:
        symbol = trade["ticker"]
        if symbol not in frames or frames[symbol].empty:
            raise ExecutionError(f"{symbol}: no execution history. No account changes saved.")
        frame = frames[symbol].copy()
        frame.index = pd.to_datetime(frame.index)
        frame = frame.sort_index()
        if frame.index.duplicated().any() or frame.index.tz is not None:
            raise ExecutionError(f"{symbol}: duplicate or timezone-ambiguous daily bars.")
        prepared[symbol] = frame
        baseline = trade.get("last_processed_session") or trade["signal_date"]
        if baseline > as_of:
            raise ExecutionError("An older snapshot cannot roll the account backwards.")
        if baseline not in frame.index.strftime("%Y-%m-%d"):
            raise ExecutionError(f"{symbol}: history no longer covers {baseline}. Restore a longer market snapshot; no dates were guessed.")
        if not expected_sessions:
            session_set.update(s for s in frame.index.strftime("%Y-%m-%d") if baseline < s <= as_of)
        if trade.get("last_processed_session"):
            row = frame.loc[pd.Timestamp(baseline)]
            if trade.get("last_bar_fingerprint") != bar_fingerprint(row):
                _review(trade, as_of, "Previously processed prices/actions were revised by the provider. Original fills retained; performance requires reconciliation.")
    # Use one chronological portfolio pass, rather than independent trade loops.
    history = {row["date"]: row for row in out["equity_history"]}
    if not history:
        first_signal = min(t["signal_date"] for t in out["trades"])
        initial = account_summary(out, prepared, first_signal)
        history[first_signal] = {"date": first_signal, "equity": initial["equity"], "cash": initial["cash"],
                                 "positions_value": initial["positions_value"], "unvalued": initial["unvalued"]}
    if any(t["status"] == "REVIEW_REQUIRED" for t in required):
        reviewed = account_summary(out, prepared, as_of)
        history[as_of] = {"date": as_of, "equity": None, "cash": reviewed["cash"],
                          "positions_value": reviewed["positions_value"], "unvalued": reviewed["unvalued"]}
    for session in sorted(s for s in session_set if s <= as_of):
        changed = False
        for trade in sorted(out["trades"], key=lambda t: (t["requested_at"], t["trade_id"])):
            baseline = trade.get("last_processed_session") or trade["signal_date"]
            if trade["status"] not in ACTIVE or session <= baseline:
                continue
            if pd.Timestamp(session) not in prepared[trade["ticker"]].index:
                raise ExecutionError(f"{trade['ticker']}: missing benchmark session {session}; processing paused rather than bridging a gap.")
            row = prepared[trade["ticker"]].loc[pd.Timestamp(session)]
            other_reservations = sum(t["allocation"] for t in out["trades"] if t["status"] == "PENDING" and t["trade_id"] != trade["trade_id"])
            limit = max(0.0, cash_balance(out) - other_reservations)
            _advance_trade(trade, row, session, limit)
            changed = True
        if changed:
            account = account_summary(out, prepared, session)
            history[session] = {"date": session, "equity": account["equity"], "cash": account["cash"],
                                "positions_value": account["positions_value"], "unvalued": account["unvalued"]}
    out["equity_history"] = [history[key] for key in sorted(history)]
    validate_ledger(out)
    return out


def validate_ledger(ledger: dict) -> None:
    if not isinstance(ledger, dict) or ledger.get("schema_version") != 2 or ledger.get("currency") != "INR":
        raise ValueError("Unsupported paper ledger. Legacy records must stay in the private unvalidated archive.")
    positive(ledger.get("initial_cash"), "Initial cash")
    trades = ledger.get("trades")
    if not isinstance(trades, list) or len(trades) > 20_000:
        raise ValueError("Invalid or oversized trade list.")
    seen, identities, active = set(), set(), set()
    for trade in trades:
        if not isinstance(trade, dict):
            raise ValueError("Every trade must be an object.")
        for field in ("trade_id", "ticker", "signal_date", "requested_at", "execution", "strategy", "audit", "dividends", "status", "sessions_held", "last_processed_session"):
            if field not in trade:
                raise ValueError(f"Trade is missing {field}.")
        if trade["status"] not in ALL_STATUSES or trade["trade_id"] in seen:
            raise ValueError("Duplicate trade ID or invalid status.")
        if not isinstance(trade["trade_id"], str) or not trade["trade_id"]:
            raise ValueError("Invalid trade ID.")
        seen.add(trade["trade_id"])
        identity = (trade["ticker"], trade["signal_date"])
        if identity in identities:
            raise ValueError("Duplicate ticker/signal-session order.")
        identities.add(identity)
        if not isinstance(trade["sessions_held"], int) or isinstance(trade["sessions_held"], bool) or trade["sessions_held"] < 0:
            raise ValueError("Invalid holding-session count.")
        if not isinstance(trade["audit"], list) or not isinstance(trade["dividends"], list):
            raise ValueError("Invalid trade audit or dividend collection.")
        for event in trade["audit"]:
            if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                raise ValueError("Invalid audit event.")
            date.fromisoformat(event["session"])
        if canonical_symbol(trade["ticker"]) != trade["ticker"]:
            raise ValueError("Trade identity is not canonical.")
        signal = date.fromisoformat(trade["signal_date"])
        requested = datetime.fromisoformat(trade["requested_at"])
        if requested.tzinfo is None:
            raise ValueError("Order timestamp must contain a timezone.")
        ExecutionConfig(**trade["execution"])
        from src.config import StrategyConfig
        StrategyConfig(**trade["strategy"])
        positive(trade.get("allocation"), "Allocation")
        positive(trade.get("atr_at_signal"), "ATR")
        positive(trade.get("reference_close"), "Reference close")
        if not 0 < trade.get("risk_pct", 0) <= 10:
            raise ValueError("Invalid trade risk budget.")
        if trade["status"] in {"PENDING", "CANCELLED"} and trade.get("entry_date"):
            raise ValueError("An unfilled order cannot contain a fill.")
        if trade.get("exit_date") and trade["status"] != "CLOSED":
            raise ValueError("Only a closed position may have an exit.")
        if trade["status"] in ACTIVE | {"REVIEW_REQUIRED"}:
            if trade["ticker"] in active:
                raise ValueError("Concurrent same-ticker positions are not allowed.")
            active.add(trade["ticker"])
        if trade.get("entry_date"):
            entry = date.fromisoformat(trade["entry_date"])
            if entry <= signal:
                raise ValueError("Entry must be after the signal session.")
            if "entry_fee" not in trade:
                raise ValueError("Entry fee is missing.")
            if trade["status"] == "CLOSED" and any(key not in trade for key in ("exit_fee", "realized_pnl", "realized_pnl_pct")):
                raise ValueError("Closed trade is missing its fee or P&L accounting.")
            quantity = trade.get("quantity")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                raise ValueError("Quantity must be a positive whole number.")
            positive(trade.get("entry_price"), "Entry price")
            positive(trade.get("stop_price"), "Stop price")
            if trade["stop_price"] >= trade["entry_price"]:
                raise ValueError("A long stop must be below entry.")
            last = date.fromisoformat(trade["last_processed_session"])
            if not 1 <= trade["sessions_held"] <= (last - entry).days + 1:
                raise ValueError("Impossible holding-session count.")
            if trade["status"] == "CLOSED":
                exit_day = date.fromisoformat(trade["exit_date"])
                if exit_day < entry or exit_day != last:
                    raise ValueError("Exit date is inconsistent with processed sessions.")
                positive(trade.get("exit_price"), "Exit price")
            for key in ("entry_fee", "exit_fee"):
                value = trade.get(key, 0)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid execution fee.")
        elif trade["status"] in {"OPEN", "CLOSED"}:
            raise ValueError("A filled position is missing entry details.")
        dividend_dates = []
        for event in trade["dividends"]:
            dividend_dates.append(date.fromisoformat(event["date"]))
            positive(event["amount"], "Dividend")
        if len(dividend_dates) != len(set(dividend_dates)):
            raise ValueError("Duplicate dividend cash event.")
        if dividend_dates and (not trade.get("entry_date") or any(d <= date.fromisoformat(trade["entry_date"]) or d > date.fromisoformat(trade["last_processed_session"]) for d in dividend_dates)):
            raise ValueError("Dividend dates fall outside the processed ownership period.")
        if trade["status"] == "CLOSED":
            basis = trade["quantity"] * trade["entry_price"] + trade["entry_fee"]
            proceeds = trade["quantity"] * trade["exit_price"] - trade["exit_fee"] + sum(d["amount"] for d in trade["dividends"])
            for key, expected in (("realized_pnl", proceeds - basis), ("realized_pnl_pct", (proceeds / basis - 1) * 100)):
                value = trade[key]
                if not isinstance(value, (int, float)) or not math.isfinite(value) or not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-6):
                    raise ValueError("Closed trade P&L does not reconcile to its cash flows.")
    if cash_balance(ledger) < -1e-6 or available_cash(ledger) < -1e-6:
        raise ValueError("Ledger violates the cash-only / reservation constraint.")
    if not isinstance(ledger.get("equity_history"), list):
        raise ValueError("Missing account history.")
    dates = []
    for point in ledger["equity_history"]:
        dates.append(date.fromisoformat(point["date"]))
        for key in ("equity", "cash", "positions_value"):
            value = point.get(key)
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError("Invalid equity history value.")
    if dates != sorted(set(dates)):
        raise ValueError("Account history must contain unique chronological dates.")
