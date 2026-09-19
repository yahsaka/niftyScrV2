from copy import deepcopy
from datetime import datetime
from dataclasses import replace
import math
import pandas as pd
import pytest
from src.backtest import simulate_trade
from src.config import ExecutionConfig
from src.execution import (ExecutionError, account_summary, available_cash, cancel_order, cash_balance,
                           create_order, new_ledger, process_ledger, size_position, validate_ledger)
from src.freshness import IST


def test_repeated_sessions_do_not_accumulate(ledger, bars):
    short = bars.head(4)
    first = process_ledger(ledger, {"INFY": short}, "2025-01-06")
    assert first["trades"][0]["status"] == "OPEN"
    assert first["trades"][0]["sessions_held"] == 3
    for _ in range(5):
        assert process_ledger(first, {"INFY": short}, "2025-01-06") == first
    assert ledger["trades"][0]["status"] == "PENDING"  # pure input, no mutation


def test_incremental_matches_single_batch(ledger, bars):
    partial = process_ledger(ledger, {"INFY": bars.head(3)}, "2025-01-03")
    later = process_ledger(partial, {"INFY": bars.head(6)}, "2025-01-08")
    batch = process_ledger(ledger, {"INFY": bars.head(6)}, "2025-01-08")
    assert later == batch
    assert later["trades"][0]["sessions_held"] == 5
    assert later["trades"][0]["exit_date"] == "2025-01-08"


def test_entry_day_stop_is_not_skipped(ledger, bars):
    bars.loc[bars.index[1], "Low"] = 85.0
    result = process_ledger(ledger, {"INFY": bars}, str(bars.index[-1].date()))
    trade = result["trades"][0]
    assert trade["status"] == "CLOSED"
    assert trade["sessions_held"] == 1
    assert trade["exit_date"] == "2025-01-02"
    assert trade["exit_reason"] == "ATR stop"


def test_gap_exit_uses_open_not_stop(ledger, bars):
    bars.loc[bars.index[2], ["Open", "Low"]] = [85.0, 84.0]
    trade = process_ledger(ledger, {"INFY": bars}, str(bars.index[-1].date()))["trades"][0]
    assert trade["exit_reason"] == "ATR stop (gap)"
    assert trade["exit_price"] == pytest.approx(85 * .9995)
    assert -trade["realized_pnl"] > trade["planned_risk"]


def test_paper_and_backtest_share_identical_fills(ledger, bars):
    bars.loc[bars.index[2], "Low"] = 89.0
    paper = process_ledger(ledger, {"INFY": bars}, str(bars.index[-1].date()))["trades"][0]
    backtest = simulate_trade(bars, 0, 5.0, ExecutionConfig(hold_sessions=5), ticker="INFY")
    for key in ("entry_date", "entry_price", "stop_price", "exit_date", "exit_price", "exit_reason", "sessions_held", "realized_pnl_pct"):
        assert paper[key] == pytest.approx(backtest[key]) if isinstance(paper[key], float) else paper[key] == backtest[key]


def test_cash_sizing_cannot_double_allocation():
    size = size_position(100000.0, 2.0, 100.0, .5)
    assert size["quantity"] <= 999
    assert size["cash_required"] <= 100000.0
    assert size["planned_risk"] <= 2000.0


@pytest.mark.parametrize("allocation, risk, opening, atr", [(0, 2, 100, 5), (100, 0, 100, 5), (100, 11, 100, 5), (100, 2, 0, 5), (100, 2, 100, 0), (100, 2, 100, 100), (float('nan'), 2, 100, 5)])
def test_invalid_sizing_rejected(allocation, risk, opening, atr):
    with pytest.raises(ValueError):
        size_position(allocation, risk, opening, atr)


def test_pending_orders_reserve_cash(ledger, setup):
    assert available_cash(ledger) == 90000
    other = {**setup, "ticker": "TCS"}
    with pytest.raises(ValueError, match="unreserved cash"):
        create_order(ledger, other, 95000., 2.)


def test_duplicate_closed_or_cancelled_signal_not_recreated(ledger, setup):
    cancelled = cancel_order(ledger, ledger["trades"][0]["trade_id"])
    assert available_cash(cancelled) == 100000
    with pytest.raises(ValueError, match="already staged"):
        create_order(cancelled, setup, 10000., 2.)


def test_same_ticker_overlap_rejected(ledger, setup):
    with pytest.raises(ValueError, match="active position"):
        create_order(ledger, {**setup, "last_date": "2025-01-02"}, 10000., 2.)


def test_manual_order_schema_processes_without_keyerror(ledger, bars):
    validate_ledger(ledger)
    result = process_ledger(ledger, {"INFY": bars}, str(bars.index[-1].date()))
    assert result["trades"][0]["status"] == "CLOSED"


def test_request_after_next_open_never_gets_retroactive_fill(setup, bars):
    late = create_order(new_ledger(), setup, 10000., 2., requested_at=datetime(2025, 1, 2, 12, tzinfo=IST))
    result = process_ledger(late, {"INFY": bars}, str(bars.index[-1].date()))
    assert result["trades"][0]["status"] == "CANCELLED"
    assert cash_balance(result) == 100000


def test_missing_execution_bar_aborts_without_mutating(ledger, bars):
    expected = list(bars.head(6).index.strftime("%Y-%m-%d"))
    missing = bars.drop(bars.index[2])
    before = deepcopy(ledger)
    with pytest.raises(ExecutionError, match="missing benchmark session"):
        process_ledger(ledger, {"INFY": missing}, "2025-01-08", expected)
    assert ledger == before


def test_revised_processed_bar_is_flagged(ledger, bars):
    first = process_ledger(ledger, {"INFY": bars.head(3)}, "2025-01-03")
    revised = bars.copy()
    revised.loc["2025-01-03", "Close"] = 103.0
    result = process_ledger(first, {"INFY": revised}, "2025-01-08")
    assert result["trades"][0]["status"] == "REVIEW_REQUIRED"
    assert account_summary(result, {"INFY": revised}, "2025-01-08")["equity"] is None


def test_split_freezes_instead_of_inventing_a_return(ledger, bars):
    bars.loc[bars.index[2], "Stock Splits"] = 2.0
    result = process_ledger(ledger, {"INFY": bars}, "2025-01-08")
    assert result["trades"][0]["status"] == "REVIEW_REQUIRED"
    assert "realized_pnl" not in result["trades"][0]


def test_dividend_applied_once_only_for_prior_owner(ledger, bars):
    bars.loc[bars.index[1], "Dividends"] = 2.0  # new ex-date buyer not entitled
    bars.loc[bars.index[2], "Dividends"] = 3.0
    result = process_ledger(ledger, {"INFY": bars}, "2025-01-08")
    trade = result["trades"][0]
    assert len(trade["dividends"]) == 1
    assert trade["dividends"][0]["amount"] == 3 * trade["quantity"]
    assert process_ledger(result, {"INFY": bars}, "2025-01-08") == result


def test_cash_equity_and_realized_pnl_reconcile(ledger, bars):
    result = process_ledger(ledger, {"INFY": bars}, "2025-01-08")
    trade = result["trades"][0]
    account = account_summary(result, {"INFY": bars}, "2025-01-08")
    assert account["equity"] == pytest.approx(100000 + trade["realized_pnl"])
    assert account["cash"] == pytest.approx(account["equity"])
    assert result["equity_history"][0]["equity"] == 100000
    assert result["equity_history"][-1]["equity"] == pytest.approx(account["equity"])


def test_open_position_without_current_mark_is_unvalued(ledger, bars):
    opened = process_ledger(ledger, {"INFY": bars.head(3)}, "2025-01-03")
    account = account_summary(opened, {}, "2025-01-03")
    assert account["equity"] is None and account["unvalued"] == ["INFY"]


def test_old_snapshot_cannot_rewind_account(ledger, bars):
    opened = process_ledger(ledger, {"INFY": bars.head(4)}, "2025-01-06")
    with pytest.raises(ExecutionError, match="older snapshot"):
        process_ledger(opened, {"INFY": bars}, "2025-01-03")


def test_impossible_legacy_session_counts_rejected(ledger, bars):
    opened = process_ledger(ledger, {"INFY": bars.head(3)}, "2025-01-03")
    opened["trades"][0]["sessions_held"] = 20
    with pytest.raises(ValueError, match="Impossible"):
        validate_ledger(opened)


def test_multiple_orders_remain_cash_constrained(ledger, setup, bars):
    second = create_order(ledger, {**setup, "ticker": "TCS"}, 90000., 2., ExecutionConfig(hold_sessions=5), requested_at=datetime(2025, 1, 1, 16, 30, tzinfo=IST))
    processed = process_ledger(second, {"INFY": bars, "TCS": bars}, "2025-01-08")
    assert cash_balance(processed) >= 0
    assert all(point["cash"] >= 0 for point in processed["equity_history"])
