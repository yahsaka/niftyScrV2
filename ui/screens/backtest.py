import json
import pandas as pd
import streamlit as st
from src.backtest import cost_sensitivity, run_event_study
from src.market import unpack_frame
from ui import charts
from ui.visuals import empty, metric_card, page_heading, panel_title, pct, status_strip
from ui.widgets import html, plot, table


def render(ctx):
    html(page_heading("Backtest", 'Test the rules. <span>Question the results.</span>',
                      "A per-ticker event study with the same next-open, stop and cost model as paper trading.", ctx.snapshot.get("as_of")))
    html(status_strip(ctx.snapshot))
    options = sorted(ticker for ticker, stock in ctx.snapshot.get("stocks", {}).items() if stock.get("rows"))
    index = unpack_frame(ctx.snapshot["index"])
    if not options or index.empty:
        with st.container(border=True, key="nq-panel-backtest-1"):
            html(empty("History comes before hypotheses", "Run a market refresh first. The snapshot retains up to 520 sessions, with indicators warmed on the full downloaded history.", "chart"))
        return
    with st.form("backtest-config"):
        selected = st.multiselect("Instruments to study (up to 20)", options, default=options[:1], max_selections=20)
        c1, c2, c3 = st.columns(3)
        earliest, latest = index.index[0].date(), index.index[-1].date()
        start_default = max(earliest, (index.index[-1] - pd.DateOffset(years=1)).date())
        start = c1.date_input("Signal window starts", start_default, min_value=earliest, max_value=latest)
        end = c2.date_input("Study ends", latest, min_value=earliest, max_value=latest)
        threshold = c3.number_input("Minimum conditions", min_value=0, max_value=6, value=ctx.strategy.qualified_min_score, step=1)
        sensitivity = st.checkbox("Also compare zero, baseline and double modeled fees (slippage unchanged).", disabled=ctx.execution.round_trip_cost_bps > 500, help="Double-fee sensitivity is available for baseline assumptions up to 500 bps; the model maximum is 1,000 bps.")
        st.caption(f"{ctx.execution.hold_sessions}-session hold · {ctx.execution.atr_multiplier:g}× ATR stop · {ctx.execution.entry_slippage_bps:g}/{ctx.execution.exit_slippage_bps:g} bps entry/exit slippage · {ctx.execution.round_trip_cost_bps:g} bps round-trip fee assumption.")
        run = st.form_submit_button("Run event study", type="primary", disabled=not selected)
    st.caption("Thresholds below the paper-qualified minimum are exploratory watchlist studies. Each ticker allows only one active trade; different tickers can overlap and reuse an independent hypothetical budget.")
    if run:
        try:
            frames = {ticker: unpack_frame(ctx.snapshot["stocks"][ticker]) for ticker in selected}
            with st.spinner("Evaluating signals and completed-session fills…"):
                report = run_event_study(frames, ctx.snapshot["regimes"], start.isoformat(), end.isoformat(), ctx.strategy, ctx.execution, int(threshold), index)
                report["snapshot_id"] = ctx.snapshot["snapshot_id"]
                report["is_demo"] = bool(ctx.snapshot.get("is_demo"))
                if sensitivity:
                    report["cost_sensitivity"] = cost_sensitivity(frames, ctx.snapshot["regimes"], start.isoformat(), end.isoformat(), ctx.strategy, ctx.execution, index, int(threshold))
            st.session_state["current-study"] = report
            if not ctx.snapshot.get("is_demo"):
                ctx.save(backtests=[*ctx.workspace["backtests"], report][-3:])
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
    report = st.session_state.get("current-study") or (ctx.workspace["backtests"][-1] if ctx.workspace["backtests"] else None)
    if not report:
        return
    if report.get("is_demo"):
        st.warning("These results use synthetic fixture prices and are not evidence of actual strategy performance.")
    st.caption(f"Displayed run: {report['start']} → {report['end']} · {len(report['tickers'])} ticker(s) · minimum {report['min_score']} conditions · snapshot {report.get('snapshot_id', 'unknown')}. These are the saved run's assumptions, not unsaved form edits.")
    summary = report["summary"]
    for col, values in zip(st.columns(4), [("Completed trades", str(summary["trades"]), "Unfinished / excluded samples reported below", "teal"),
                                         ("Positive-return trades", pct(summary["win_rate"]), "Descriptive sample rate, not a forecast", ""),
                                         ("Mean net trade return", pct(summary["mean_return_pct"], True), "Average of individual completed samples", "lime"),
                                         ("Median trade return", pct(summary["median_return_pct"], True), "Not a portfolio-level return", "")]):
        with col:
            html(metric_card(*values))
    if report["trades"]:
        left, right = st.columns([1.5, 1])
        with left:
            with st.container(border=True, key="nq-panel-backtest-2"):
                html(panel_title("The distribution matters", "Frequency of net returns across completed event-study trades"))
                plot(charts.return_histogram(report["trades"], ctx.dark), "study-distribution")
        with right:
            with st.container(border=True, key="nq-panel-backtest-3"):
                html(panel_title("A different lens", "Matching Nifty 50 open-to-close windows; no benchmark fees"))
                st.write(f"**{pct(summary['mean_benchmark_pct'], True)}** average benchmark-window return")
                factor = summary["profit_factor"]
                st.write(f"Return-based profit factor: **{factor:.2f}**" if factor is not None else "Return-based profit factor: **not defined** (no loss denominator).")
                split = report["chronological_split"]
                st.caption(f"Chronological split at {split['split_date']}. This is a descriptive 70/30 split, not an optimized walk-forward test.")
                st.write(f"Earlier: {split['earlier']['trades']} trades · mean {pct(split['earlier']['mean_return_pct'], True)}")
                st.write(f"Later: {split['later']['trades']} trades · mean {pct(split['later']['mean_return_pct'], True)}")
        table(report["trades"], [{"key": "ticker", "label": "Symbol"}, {"key": "signal_date", "label": "Signal"},
                                 {"key": "score", "label": "Conditions", "format": "score"}, {"key": "entry_date", "label": "Entry"},
                                 {"key": "exit_date", "label": "Exit"}, {"key": "realized_pnl_pct", "label": "Net return", "format": "pct"},
                                 {"key": "benchmark_return_pct", "label": "Benchmark", "format": "pct"}, {"key": "exit_reason", "label": "Exit reason"}],
              "study-trades", ctx.dark)
    else:
        html(empty("No completed qualifying samples", "This is not a zero-return result. Review the signal threshold, market regime and available observation window.", "search"))
    if report.get("cost_sensitivity"):
        with st.expander("Fee sensitivity", expanded=True):
            table(report["cost_sensitivity"], [{"key": "cost_bps", "label": "Round-trip fee bps", "format": "number"},
                                              {"key": "trades", "label": "Samples", "format": "number"},
                                              {"key": "mean_return_pct", "label": "Mean net return", "format": "pct"},
                                              {"key": "win_rate", "label": "Positive-return share", "format": "pct"}], "cost-sensitivity", ctx.dark)
    st.caption(f"Excluded: {report['skipped']['unfinished']} unfinished, {report['skipped']['corporate_action']} corporate-action cases, {report['skipped']['unfundable']} unsized entries. Data errors: {len(report['errors'])}.")
    with st.expander("Methodology, exclusions & saved assumptions"):
        for limitation in report["limitations"]:
            st.write(limitation)
        st.json({"strategy": report["strategy"], "execution": report["execution"], "errors": report["errors"]})
    st.download_button("Download full study JSON", json.dumps(report, indent=2, allow_nan=False), "nifty-event-study.json", "application/json")
