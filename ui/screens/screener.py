from copy import deepcopy
from datetime import datetime
import hashlib
from html import escape
import json
import streamlit as st
from src.execution import available_cash, create_order, size_position
from src.freshness import freshness, order_window
from src.market import unpack_frame
from src.screener import RULES, filter_signals
from ui import charts
from ui.visuals import empty, money, page_heading, panel_title, pct, rules_html, status_strip
from ui.widgets import html, plot, table


def reset_filters(min_score):
    st.session_state["screen-query"] = ""
    st.session_state["screen-score"] = min_score
    st.session_state["screen-industry"] = "All industries"
    st.session_state["screen-preset"] = "All setups"
    st.session_state["screen-triggers"] = []
    st.session_state["selected_ticker"] = None


def render(ctx):
    html(page_heading("Screener", 'Find the signal. <span>See the evidence.</span>',
                      "One universe. Six transparent conditions. Your research shortlist.", ctx.snapshot.get("as_of")))
    html(status_strip(ctx.snapshot))
    with st.container(border=True, key="nq-panel-screener-filters"):
        c1, c2, c3 = st.columns([2, 1.2, 1.2])
        with c1:
            query = st.text_input("Search company or symbol", placeholder="Try Infosys or INFY…", key="screen-query")
        with c2:
            industries = ["All industries", *sorted({row.get("industry", "Unknown") for row in ctx.signals})]
            if st.session_state.get("screen-industry") not in industries:
                st.session_state["screen-industry"] = industries[0]
            industry = st.selectbox("Industry", industries, key="screen-industry")
        with c3:
            score = st.slider("Minimum conditions", 0, 6, ctx.strategy.watchlist_min_score, key="screen-score")
            st.caption(f"{score} of 6 conditions")
        preset = st.segmented_control("View", ["All setups", "Qualified", "Breakouts", "My watchlist"], default="All setups", key="screen-preset") or "All setups"
        with st.expander("Specific conditions & saved views"):
            triggers = st.multiselect("Require all selected conditions", list(RULES), format_func=lambda key: RULES[key][0], key="screen-triggers")
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Save this view as", max_chars=40, placeholder="My trend scan")
                if st.button("Save view", disabled=not name.strip()):
                    saved = deepcopy(ctx.workspace["saved_filters"])
                    saved[name.strip()] = {"query": query, "industry": industry, "score": score, "preset": preset, "triggers": triggers}
                    ctx.save(saved_filters=saved)
                    st.success("View saved in this workspace. Include it in your next backup.")
            with c2:
                saved_names = list(ctx.workspace["saved_filters"])
                saved_name = st.selectbox("Saved views", saved_names, index=0 if saved_names else None, disabled=not saved_names)
                def restore_view():
                    saved = ctx.workspace["saved_filters"][saved_name]
                    for source, target in (("query", "screen-query"), ("industry", "screen-industry"), ("score", "screen-score"), ("preset", "screen-preset"), ("triggers", "screen-triggers")):
                        st.session_state[target] = saved[source]
                st.button("Apply saved view", disabled=not saved_names, on_click=restore_view)
    statuses = ["Trade-Ready"] if preset == "Qualified" else None
    required = list(triggers)
    if preset == "Breakouts" and "EMA_200_BREAKOUT" not in required:
        required.append("EMA_200_BREAKOUT")
    rows = filter_signals(ctx.signals, query, statuses, score, None if industry == "All industries" else [industry], required)
    if preset == "My watchlist":
        rows = [row for row in rows if row["ticker"] in ctx.workspace["watchlist"]]
    c1, c2, c3 = st.columns([3, 1, 1])
    c1.caption(f"{len(rows)} matching setups · {len(ctx.signals)} in the snapshot · scan uses your saved rule thresholds")
    c2.button("Reset filters", width="stretch", on_click=reset_filters, args=(ctx.strategy.watchlist_min_score,))
    import pandas as pd
    export_rows = [{**row, "status": "Qualified" if row.get("status") == "Trade-Ready" else row.get("status")} for row in rows]
    c3.download_button("Export results", pd.DataFrame(export_rows).drop(columns=["checks", "triggers"], errors="ignore").to_csv(index=False),
                       file_name="nifty-filtered-setups.csv", mime="text/csv", disabled=not rows, width="stretch")
    tickers = [row["ticker"] for row in rows]
    if st.session_state.get("selected_ticker") not in tickers:
        st.session_state["selected_ticker"] = None
    if not rows:
        with st.container(border=True, key="nq-panel-screener-1"):
            html(empty("No matches. Nothing hidden.", "Adjust your filters or return after a new scan. Stocks outside these results will not appear in the analysis panel.", "search"))
        return
    # Component return values carry immutable ticker IDs, not positions in a sorted UI.
    fingerprint = hashlib.sha256(json.dumps(tickers).encode()).hexdigest()[:10] + ctx.snapshot["snapshot_id"]
    picker_key = "screen-pick-" + fingerprint
    selected = st.session_state.get("selected_ticker")
    left, right = st.columns([2.05, 1], gap="medium")
    with left:
        with st.container(border=True, key="nq-panel-screener-results"):
            html(panel_title("The shortlist", "Click a row, or use the accessible selector below the table."))
            event = table(rows, [
                {"key": "ticker", "label": "Company", "subkey": "company"},
                {"key": "close", "label": "Close", "format": "money", "decimals": 2, "align": "right"},
                {"key": "score", "label": "Conditions", "format": "score"},
                {"key": "volume_ratio", "label": "Volume", "format": "ratio", "align": "right"},
                {"key": "status", "label": "Setup", "format": "status"},
            ], "screen-table-" + fingerprint, ctx.dark, selected, True, 460)
            if event and event != st.session_state.get("last-table-event") and event["id"] in tickers:
                st.session_state["last-table-event"] = event
                st.session_state[picker_key] = event["id"]
            elif selected and picker_key not in st.session_state:
                st.session_state[picker_key] = selected
            with st.expander("Choose a stock manually · keyboard fallback"):
                selected = st.selectbox("Stock to inspect", tickers, index=None, key=picker_key, placeholder="Choose a stock to inspect")
            st.session_state["selected_ticker"] = selected
            st.caption("Research scores describe overlapping conditions, not independent evidence or calibrated confidence.")
    with right:
        with st.container(border=True, key="nq-panel-setup-rules"):
            if not selected:
                html(empty("See why it qualified", "Choose a result to inspect its six conditions, chart and paper-position assumptions.", "chart"))
            else:
                setup = next(row for row in rows if row["ticker"] == selected)
                html(f'<div class="nq-eyebrow">CONDITIONS MET · {setup["score"]} / 6</div><div class="nq-symbol">{escape(selected)}</div><div class="nq-company">{escape(setup.get("company", selected))} · {escape(setup.get("industry", ""))}</div>')
                html(rules_html(setup, RULES))
                watchlist = ctx.workspace["watchlist"]
                saved = selected in watchlist
                if st.button("Remove from watchlist" if saved else "Save to watchlist", width="stretch", key="save-ticker"):
                    ctx.save(watchlist=[symbol for symbol in watchlist if symbol != selected] if saved else [*watchlist, selected])
                    st.rerun()
    if selected:
        setup = next(row for row in rows if row["ticker"] == selected)
        render_analysis(ctx, setup)


def render_analysis(ctx, setup):
    frame = unpack_frame(ctx.snapshot["stocks"][setup["ticker"]])
    left, right = st.columns([2.05, 1], gap="medium")
    with left:
        with st.container(border=True, key="nq-panel-stock-chart"):
            html(panel_title(f"{setup['ticker']} · the setup in context", "Adjusted analysis prices; the execution model uses provider OHLC units."))
            period = st.segmented_control("Chart range", ["1M", "3M", "6M", "1Y", "All"], default="6M", key="stock-range") or "6M"
            plot(charts.price_chart(frame, ctx.dark, period), "stock-price-chart")
            indicator = st.segmented_control("Supporting indicator", ["Volume", "RSI", "MACD"], default="Volume", key="stock-indicator") or "Volume"
            plot(charts.indicator_chart(frame, indicator, ctx.dark, period), "stock-indicator-chart")
    with right:
        with st.container(border=True, key="nq-panel-position-plan"):
            html(panel_title("Model a paper position", f"Signal session · {setup['last_date']}"))
            html(f'<div class="nq-price">{money(setup["close"], 2)}</div><div class="nq-panel-sub">Reference close · not an executable quote</div>')
            rsi = f"{setup['rsi_14']:.1f}" if setup.get("rsi_14") is not None else "unavailable"
            volume = f"{setup['volume_ratio']:.2f}×" if setup.get("volume_ratio") is not None else "unavailable"
            st.caption(f"RSI {rsi} · {volume} average volume · {pct(setup['pct_above_50'], True)} vs 50 EMA")
            available = max(0.0, available_cash(ctx.workspace["ledger"]))
            state = freshness(ctx.snapshot.get("as_of"))
            window, reason = order_window(setup["last_date"])
            qualifies = setup["score"] >= ctx.strategy.qualified_min_score
            duplicate = any(t["ticker"] == setup["ticker"] and (t["signal_date"] == setup["last_date"] or t["status"] in {"OPEN", "PENDING", "REVIEW_REQUIRED"}) for t in ctx.workspace["ledger"]["trades"])
            allowed = state["is_fresh"] and window and qualifies and not ctx.snapshot.get("is_demo") and not duplicate and available > 0
            with st.form("paper-order"):
                allocation = st.number_input("Cash allocation (₹)", min_value=1.0, max_value=max(available, 1.0), value=min(10_000.0, max(available, 1.0)), step=500.0)
                risk_pct = st.number_input("Planned risk / allocation (%)", min_value=.1, max_value=10.0, value=2.0, step=.1)
                submitted = st.form_submit_button("Stage next-open paper order", type="primary", width="stretch", disabled=not allowed)
            try:
                estimate = size_position(allocation, risk_pct, setup["close"], setup["atr_at_signal"], ctx.execution)
                st.write(f"**{estimate['quantity']} shares** · estimated cash {money(estimate['cash_required'])}")
                st.caption(f"Provisional stop {money(estimate['stop_price'], 2)} · planned loss at modeled stop {money(estimate['planned_risk'])}. Quantity and stop are recalculated at the actual next open.")
            except (ValueError, TypeError):
                st.warning("This setup cannot currently be sized with a valid ATR and cash allocation.")
            st.caption(f"Unreserved cash: {money(available)}. Hold: {ctx.execution.hold_sessions} sessions · stop: {ctx.execution.atr_multiplier:g}× ATR.")
            st.warning("A stop is not a guaranteed maximum loss. Gaps and execution costs can increase losses. No broker order is sent.")
            if not allowed:
                message = "Synthetic preview cannot create personal paper trades." if ctx.snapshot.get("is_demo") else "This ticker/session already has an order or active position." if duplicate else "Refresh stale or missing data before staging." if not state["is_fresh"] else f"Only setups with at least {ctx.strategy.qualified_min_score} conditions qualify." if not qualifies else reason
                st.caption(message)
            if submitted:
                try:
                    ledger = create_order(ctx.workspace["ledger"], setup, allocation, risk_pct, ctx.execution, ctx.strategy)
                    ctx.save(ledger=ledger)
                    st.toast("Pending paper order staged. Export a backup to keep it.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
