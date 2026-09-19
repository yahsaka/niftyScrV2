import streamlit as st
from src.market import coverage, unpack_frame
from ui import charts
from ui.visuals import (coverage_card, empty, metric_card, page_heading, panel_title,
                        pretty_date, regime_card, status_strip)
from ui.widgets import go_to, html, plot, table


def render(ctx):
    snapshot = ctx.snapshot
    html(page_heading("Your daily research workspace", 'Your market. <span>A clearer view.</span>',
                      "Find the setup. Understand the conditions. Keep risk in perspective.", snapshot.get("as_of")))
    html(status_strip(snapshot))
    index = unpack_frame(snapshot["index"])
    counts = coverage(snapshot)
    qualified = sum(row["status"] == "Trade-Ready" for row in ctx.signals)
    watchlist = sum(row["status"] == "Watchlist" for row in ctx.signals)
    left, center, right = st.columns([1.05, 1.65, .92], gap="medium")
    with left:
        html(regime_card(snapshot, index))
        st.button("Explore the screener  ↗", type="primary", width="stretch", on_click=go_to, args=("Screener",))
    with center:
        with st.container(border=True, key="nq-panel-overview-market"):
            html(panel_title("The market, in context", "Nifty 50 and its long-term trend baseline"))
            period = st.segmented_control("Benchmark range", ["3M", "6M", "1Y"], default="6M", label_visibility="collapsed", key="overview-range") or "6M"
            if index.empty:
                html(empty("Your first scan starts here", "Run the Daily Market Snapshot workflow on GitHub, or refresh market data in Settings.", "chart"))
            else:
                plot(charts.index_chart(index, ctx.dark, period), "overview-index-chart")
    with right:
        html(metric_card("Qualified setups", str(qualified), f"{ctx.strategy.qualified_min_score}–6 conditions met · not a win probability", "lime", "scan"))
        html(metric_card("On the radar", str(watchlist), f"Watchlist · at least {ctx.strategy.watchlist_min_score} conditions met", "", "search"))
    left, right = st.columns([2.72, .92], gap="medium")
    with left:
        with st.container(border=True, key="nq-panel-overview-setups"):
            html(panel_title("Research shortlist", "Select a stock to see the complete rule breakdown."))
            if ctx.signals:
                event = table(ctx.signals[:6], [
                    {"key": "ticker", "label": "Company", "subkey": "company"},
                    {"key": "close", "label": "Close", "format": "money", "decimals": 2, "align": "right"},
                    {"key": "score", "label": "Conditions", "format": "score"},
                    {"key": "status", "label": "Setup", "format": "status"},
                ], key="overview-shortlist-" + snapshot["snapshot_id"], dark=ctx.dark, selectable=True, max_height=440)
                if event and event != st.session_state.get("last-overview-event"):
                    st.session_state["last-overview-event"] = event
                    go_to("Screener", event["id"])
                    st.rerun()
            else:
                regime = snapshot.get("market_regime")
                title = "The filter is taking a pause" if regime == "Bearish" else "No setups to display"
                body = "The broader-market rule currently suspends long setup classification. No result is also useful information." if regime == "Bearish" else "A completed, valid market snapshot is required. No example trades or returns are included in the real workspace."
                html(empty(title, body))
            st.caption("A condition count explains a model output. It is not an investment recommendation.")
    with right:
        html(coverage_card(counts))
    if not snapshot.get("as_of"):
        st.info("Start with Settings → Data & refresh. The application is fully navigable before its first market download.")
    elif counts["unassessed"]:
        st.warning(f"{counts['unassessed']} of {counts['universe']} instruments are not currently analyzed. Missing coverage is not a healthy signal.")
    comparison = snapshot.get("comparison_as_of")
    if comparison and comparison != snapshot.get("as_of"):
        added = snapshot.get("new_qualified", [])
        st.caption(f"Compared with the saved {pretty_date(comparison)} default-rule scan: {len(added)} newly qualified tickers. Changes in saved UI thresholds are not included in that comparison.")
