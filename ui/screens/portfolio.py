from copy import deepcopy
import hashlib
import json
import pandas as pd
import streamlit as st
from src.imports import infer_mapping, merge_holdings, normalize_rows, number, read_upload
from src.portfolio import analyze_holdings
from ui import charts
from ui.visuals import empty, metric_card, money, page_heading, panel_title, pct, status_strip
from ui.widgets import html, plot, table


def render(ctx):
    html(page_heading("Portfolio", 'The full picture. <span>Not just the winners.</span>',
                      "Review your invested capital, concentration and the holdings that still need data.", ctx.snapshot.get("as_of")))
    html(status_strip(ctx.snapshot))
    st.caption("Personal holdings stay in this workspace, not in GitHub. P&L is price-only and does not include dividends or personal brokerage/tax costs.")
    report = analyze_holdings(ctx.workspace["holdings"], ctx.snapshot)
    cols = st.columns(4)
    cards = [("Invested capital", money(report["invested"]), f"{len(report['rows'])} holdings · imported cost basis", "teal"),
             ("Marked value", money(report["priced_value"]) if report["priced_basis"] else "—", "Only holdings priced in this snapshot", ""),
             ("P&L · priced holdings", money(report["priced_pnl"]) if report["priced_basis"] else "—", pct(report["priced_pnl_pct"], True) + " on comparable priced cost", "lime"),
             ("Price coverage", pct(report["price_coverage_pct"]), "Weighted by invested cost, not row count", "")]
    for col, values in zip(cols, cards):
        with col:
            html(metric_card(*values))
    if report["rows"]:
        if report["unpriced"] or report["unassessed"]:
            st.warning(f"{report['unpriced']} holdings are unpriced and {report['unassessed']} are not trend-assessed. Partial coverage is not a healthy-portfolio conclusion.")
        left, right = st.columns([2, 1])
        with left:
            with st.container(border=True, key="nq-panel-portfolio-1"):
                html(panel_title("Your holdings", "All valuations use the displayed snapshot date; no separate live-price requests."))
                table(report["rows"], [
                    {"key": "ticker", "label": "Holding", "subkey": "company"},
                    {"key": "quantity", "label": "Qty", "format": "number", "align": "right"},
                    {"key": "value", "label": "Value", "format": "money", "align": "right"},
                    {"key": "pnl_pct", "label": "P&L", "format": "pct", "align": "right"},
                    {"key": "weight_pct", "label": "Cost weight", "format": "number", "align": "right"},
                    {"key": "trend", "label": "Trend", "format": "status"},
                ], "holdings-table", ctx.dark)
                st.download_button("Export valued holdings", pd.DataFrame(report["rows"]).to_csv(index=False), "nifty-holdings-PRIVATE.csv", "text/csv")
        with right:
            with st.container(border=True, key="nq-panel-portfolio-2"):
                html(panel_title("Concentration", "Top industries · invested cost, not current market value"))
                sectors = pd.DataFrame(report["rows"]).groupby("industry")["invested"].sum().sort_values().tail(6)
                plot(charts.bars(sectors.index.tolist(), sectors.values.tolist(), ctx.dark, "Invested (₹)", True), "portfolio-concentration")
                st.caption(f"Trend-assessed cost coverage: {pct(report['analysis_coverage_pct'])}. A 200 EMA comparison is only one view of exposure.")
    else:
        with st.container(border=True, key="nq-panel-portfolio-3"):
            html(empty("Your portfolio, in one place", "Import a CSV/XLSX or add a holding below. Your real workspace starts empty, never with example positions.", "wallet"))
    with st.expander("Import holdings · CSV / XLSX", expanded=not report["rows"]):
        render_import(ctx)
    with st.expander("Add or remove a holding"):
        c1, c2 = st.columns(2)
        with c1:
            with st.form("manual-holding"):
                ticker = st.selectbox("NSE instrument", sorted(ctx.registry.records), index=None, format_func=lambda key: f"{key} · {ctx.registry.records[key]['company']}")
                quantity = st.number_input("Shares", min_value=1, value=1, step=1)
                average = st.number_input("Average purchase price (₹)", min_value=.01, value=100.0, step=1.0)
                add = st.form_submit_button("Add holding", disabled=ctx.snapshot.get("is_demo", False))
            if add and ticker:
                row = {**ctx.registry.records[ticker], "quantity": int(quantity), "average_price": average}
                ctx.save(holdings=merge_holdings(ctx.workspace["holdings"], [row]))
                st.rerun()
        with c2:
            removed = st.multiselect("Holdings to remove", [row["ticker"] for row in ctx.workspace["holdings"]])
            confirm = st.checkbox("I have a backup of these holdings.", key="remove-confirm")
            if st.button("Remove selected holdings", disabled=not removed or not confirm):
                ctx.save(holdings=[row for row in ctx.workspace["holdings"] if row["ticker"] not in removed])
                st.rerun()


def render_import(ctx):
    st.write("Map columns, review the preview, and resolve unmatched rows before applying changes.")
    st.download_button("Download CSV template", "Symbol,Quantity,Average Price\nINFY,10,1500\nTCS,5,3500\n", "holdings-template.csv", "text/csv")
    uploaded = st.file_uploader("Broker holdings export", type=["csv", "xlsx"], key="portfolio-file")
    if uploaded is None:
        return
    try:
        digest = hashlib.sha256(uploaded.getvalue()).hexdigest()
        if st.session_state.get("import-digest") != digest:
            st.session_state["import-frame"] = read_upload(uploaded, uploaded.name)
            st.session_state["import-digest"] = digest
            st.session_state["import-overrides"] = {}
        frame = st.session_state["import-frame"]
        inferred = infer_mapping(frame.columns)
        mapping = {}
        for col, (field, label) in zip(st.columns(3), (("instrument", "Symbol / company / ISIN"), ("quantity", "Quantity"), ("average_price", "Average purchase price"))):
            with col:
                choices = list(frame.columns)
                mapping[field] = st.selectbox(label, choices, index=choices.index(inferred[field]) if field in inferred else None, key=f"map-{field}-{digest[:8]}")
        if not all(mapping.values()):
            st.info("Select all three source columns to continue.")
            return
        result = normalize_rows(frame, mapping, ctx.registry, st.session_state["import-overrides"])
        st.caption(f"{len(frame)} source rows · {len(result.accepted)} unique matched instruments · {len(result.rejected)} rows needing review")
        if result.accepted:
            table(result.accepted[:12], [
                {"key": "ticker", "label": "Matched instrument", "subkey": "company"},
                {"key": "quantity", "label": "Quantity", "format": "number", "align": "right"},
                {"key": "average_price", "label": "Average cost", "format": "money", "decimals": 2, "align": "right"},
            ], "import-preview-" + digest, ctx.dark, max_height=330)
        partial = False
        if result.rejected:
            table(result.rejected, [{"key": "row", "label": "Row"}, {"key": "instrument", "label": "Input"}, {"key": "reason", "label": "Needs correction"}], "import-rejected-" + digest, ctx.dark, max_height=250)
            with st.form("repair-row"):
                row_number = st.selectbox("Source row to correct", [row["row"] for row in result.rejected])
                c1, c2, c3 = st.columns([2, 1, 1])
                symbol = c1.selectbox("Correct instrument", sorted(ctx.registry.records), index=None)
                quantity = c2.number_input("Correct quantity", min_value=1, value=1, step=1)
                average = c3.number_input("Correct average price", min_value=.01, value=100.0)
                corrected = st.form_submit_button("Apply row correction")
            if corrected and symbol:
                st.session_state["import-overrides"][str(row_number - 1)] = {"instrument": symbol, "quantity": quantity, "average_price": average}
                st.rerun()
            partial = st.checkbox(f"Import valid rows only and leave {len(result.rejected)} rejected rows unapplied.")
        mode = st.radio("Apply to portfolio", ["Replace current holdings", "Add to current holdings"], horizontal=True)
        applied_key = hashlib.sha256(json.dumps([digest, mapping, st.session_state["import-overrides"], mode], sort_keys=True).encode()).hexdigest()
        already_applied = ctx.workspace["preferences"].get("last_import_digest") == applied_key
        can_apply = bool(result.accepted) and (not result.rejected or partial) and not already_applied and not ctx.snapshot.get("is_demo")
        acknowledged = st.checkbox("I reviewed the mapped quantities and costs, and have backed up any existing holdings.")
        if st.button("Apply reviewed import", type="primary", disabled=not can_apply or not acknowledged):
            holdings = result.accepted if mode.startswith("Replace") else merge_holdings(ctx.workspace["holdings"], result.accepted)
            prefs = {**ctx.workspace["preferences"], "last_import_digest": applied_key}
            ctx.save(holdings=holdings, preferences=prefs)
            st.toast("Reviewed holdings imported. Download an updated private backup.")
            st.rerun()
        if already_applied:
            st.success("This reviewed import has already been applied; duplicate import is blocked.")
    except (ValueError, KeyError, TypeError) as exc:
        st.error(str(exc))
