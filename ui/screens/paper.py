import json
import pandas as pd
import streamlit as st
from src.execution import account_summary, cancel_order
from src.market import unpack_frame
from src.paper_trader import process_snapshot
from src.storage import export_backup
from ui import charts
from ui.visuals import empty, metric_card, money, page_heading, panel_title, pct, status_strip
from ui.widgets import html, plot, table


def render(ctx):
    html(page_heading("Paper trading", 'Track the process. <span>Not the promise.</span>',
                      "A cash-only simulation with explicit fills, costs and an audit trail. No live orders.", ctx.snapshot.get("as_of")))
    html(status_strip(ctx.snapshot))
    ledger = ctx.workspace["ledger"]
    has_active = any(t["status"] in {"OPEN", "PENDING"} for t in ledger["trades"])
    auto = ctx.workspace["preferences"].get("auto_process", True)
    snapshot_key = (ctx.snapshot["snapshot_id"], ctx.workspace["revision"])
    if auto and has_active and ctx.snapshot.get("as_of") and not ctx.snapshot.get("is_demo") and st.session_state.get("paper-processed-key") != snapshot_key:
        st.session_state["paper-processed-key"] = snapshot_key
        try:
            updated = process_snapshot(ledger, ctx.snapshot)
            if updated != ledger:
                ctx.save(ledger=updated)
                ledger = updated
                st.toast("Completed sessions processed. Export an updated backup.")
        except ValueError as exc:
            st.warning(str(exc))
    frames = {ticker: unpack_frame(stock) for ticker, stock in ctx.snapshot.get("stocks", {}).items()
              if any(t["ticker"] == ticker for t in ledger["trades"]) and stock.get("quality") == "Current"}
    account = account_summary(ledger, frames, ctx.snapshot.get("as_of"))
    cols = st.columns(4)
    cards = [("Account equity", money(account["equity"]), "Cash + currently valued open positions", "teal"),
             ("Available cash", money(account["available_cash"]), "After reserving pending-order allocations", "lime"),
             ("Realized P&L", money(account["realized_pnl"]), "Closed positions · net of modeled costs", ""),
             ("Unrealized P&L", money(account["unrealized_pnl"]), "Price mark less entry basis · before exit costs", "")]
    for col, values in zip(cols, cards):
        with col:
            html(metric_card(*values))
    if account["unvalued"]:
        st.error("Account equity is not fully valued: " + ", ".join(account["unvalued"]) + ". Missing or revised data is not treated as zero exposure.")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.caption(f"Cash balance {money(account['cash'])} · initial cash {money(ledger['initial_cash'])} · dividend cash credited {money(account['dividends'])}")
    with c2:
        st.download_button("Download private workspace backup", export_backup(ctx.workspace), "nifty-workspace-PRIVATE.json", "application/json", width="stretch")
    with st.container(border=True, key="nq-panel-paper-equity"):
        html(panel_title("Your simulated account", "Actual cash and quantities; individual trade percentages are never added into an equity curve."))
        if ledger["equity_history"]:
            plot(charts.equity_chart(ledger["equity_history"], ledger["initial_cash"], ctx.dark), "paper-equity-chart")
            st.caption("Marked at completed session closes. Costs are charged on fills; expected exit fees and future dividends are not pre-deducted. Gaps in valuation remain gaps.")
        else:
            html(empty("A clean ledger. A reliable start.", "Qualified setups can be staged from the Screener. Existing legacy trades are archived separately and excluded from all performance.", "chart"))
    c1, c2 = st.columns([3, 1])
    with c1:
        view = st.segmented_control("Ledger view", ["Open", "Pending", "Closed", "Cancelled", "Needs review"], default="Open", key="ledger-view") or "Open"
    with c2:
        if st.button("Process completed sessions", disabled=not has_active or not ctx.snapshot.get("as_of") or bool(ctx.snapshot.get("is_demo")), width="stretch"):
            try:
                ctx.save(ledger=process_snapshot(ledger, ctx.snapshot))
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    statuses = {"Open": "OPEN", "Pending": "PENDING", "Closed": "CLOSED", "Cancelled": "CANCELLED", "Needs review": "REVIEW_REQUIRED"}
    rows = [trade for trade in ledger["trades"] if trade["status"] == statuses[view]]
    columns = [{"key": "ticker", "label": "Symbol"}, {"key": "signal_date", "label": "Signal session"}]
    if view == "Pending":
        columns += [{"key": "allocation", "label": "Reserved cash", "format": "money", "align": "right"}, {"key": "reference_close", "label": "Reference close", "format": "money", "decimals": 2}]
    elif view in {"Open", "Closed"}:
        columns += [{"key": "quantity", "label": "Qty", "format": "number", "align": "right"}, {"key": "entry_price", "label": "Entry", "format": "money", "decimals": 2}, {"key": "sessions_held", "label": "Sessions", "format": "number"}]
        if view == "Closed":
            columns += [{"key": "exit_date", "label": "Exit session"}, {"key": "realized_pnl_pct", "label": "Net return", "format": "pct"}, {"key": "exit_reason", "label": "Reason"}]
        else:
            columns += [{"key": "stop_price", "label": "Stop", "format": "money", "decimals": 2}, {"key": "last_processed_session", "label": "Processed through"}]
    elif view == "Cancelled":
        columns += [{"key": "cancel_reason", "label": "Reason"}]
    else:
        columns += [{"key": "review_reason", "label": "Reconciliation needed"}]
    with st.container(border=True, key="nq-panel-paper-1"):
        if rows:
            table(rows, columns, "paper-table-" + view, ctx.dark)
        else:
            html(empty(f"No {view.lower()} positions", "The ledger only displays records generated by the corrected execution model.", "folder"))
    pending = [t for t in ledger["trades"] if t["status"] == "PENDING"]
    if pending:
        with st.expander("Cancel a pending order"):
            chosen = st.selectbox("Pending order", [t["trade_id"] for t in pending], format_func=lambda key: next(f"{t['ticker']} · {t['signal_date']}" for t in pending if t["trade_id"] == key))
            if st.button("Cancel selected pending order"):
                ctx.save(ledger=cancel_order(ledger, chosen))
                st.rerun()
    if ledger["trades"]:
        with st.expander("Inspect execution assumptions & audit history"):
            selected = st.selectbox("Trade to inspect", [t["trade_id"] for t in ledger["trades"]], format_func=lambda key: next(f"{t['ticker']} · {t['signal_date']} · {t['status']}" for t in ledger["trades"] if t["trade_id"] == key))
            trade = next(t for t in ledger["trades"] if t["trade_id"] == selected)
            table(trade["audit"], [{"key": "session", "label": "Session"}, {"key": "event", "label": "Event"}], "paper-audit-" + selected, ctx.dark, max_height=320)
            st.json({key: trade[key] for key in ("strategy_version", "execution", "requested_at", "source")})
        st.download_button("Export ledger JSON", json.dumps(ledger, indent=2), "paper-ledger-PRIVATE.json", "application/json")
    st.info("GitHub updates market data only. Personal orders catch up when you open this screen (if automatic processing is enabled) or press Process. Free-host session data must be backed up before closing or redeploying.")
