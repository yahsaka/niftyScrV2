from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import streamlit as st
from src.config import ExecutionConfig, StrategyConfig
from src.execution import new_ledger
from src.market import ROOT, coverage, save_snapshot
from src.pipeline import build_snapshot
from src.screener import RULES
from src.storage import LocalStore, export_backup, import_backup
from ui.visuals import metric_card, money, page_heading, panel_title, pretty_date, status_strip
from ui.widgets import html, table


@st.cache_resource
def refresh_lock():
    return threading.Lock()


def render(ctx):
    html(page_heading("Workspace settings", 'Make it yours. <span>Keep it understood.</span>',
                      "Manage personal backups, data quality and the assumptions behind every result.", ctx.snapshot.get("as_of")))
    html(status_strip(ctx.snapshot))
    section = st.segmented_control("Settings section", ["Workspace", "Data & refresh", "Model settings", "Learn"], default="Workspace", key="settings-section") or "Workspace"
    if section == "Workspace":
        workspace_settings(ctx)
    elif section == "Data & refresh":
        data_settings(ctx)
    elif section == "Model settings":
        model_settings(ctx)
    else:
        learn(ctx)


def workspace_settings(ctx):
    local = isinstance(ctx.store, LocalStore)
    with st.container(border=True, key="nq-panel-settings-1"):
        html(panel_title("Your workspace, your responsibility", "No paid database, external account service or broker connection."))
        if local:
            st.warning("Local SQLite mode is enabled. It is one shared personal workspace on this server, not a multiuser account system. Only use it on a trusted local/private deployment. Free-host files can still disappear.")
        else:
            st.info("Session mode: personal data lives in server memory for this browser session. It is not committed to GitHub or saved permanently. A browser reload, disconnected session, restart or redeploy can lose it. Download a backup regularly.")
        st.caption("This release has no application login. Session isolation is not authentication. Use host-level private visibility or a trusted local machine for sensitive data.")
        st.download_button("Download full private workspace backup", export_backup(ctx.workspace), "nifty-workspace-PRIVATE.json", "application/json", type="primary")
        st.caption("Plain JSON, not encrypted. Includes holdings, watchlist, settings, paper records and the last three studies. Keep it off public repositories.")
    with st.expander("Restore a workspace backup"):
        uploaded = st.file_uploader("Version-2 workspace JSON", type=["json"], key="restore-file")
        if uploaded:
            try:
                restored = import_backup(uploaded.getvalue())
                st.write(f"**{len(restored['holdings'])} holdings** · **{len(restored['ledger']['trades'])} paper records** · initial cash **{money(restored['ledger']['initial_cash'])}**")
                acknowledged = st.checkbox("Replace this workspace with the verified backup. I have saved a copy of the current workspace.")
                if st.button("Restore this backup", disabled=not acknowledged or bool(ctx.snapshot.get("is_demo"))):
                    restored["revision"] = ctx.workspace["revision"]
                    ctx.store.save(restored)
                    st.session_state["_pending_theme"] = restored["preferences"].get("dark_mode", False)
                    st.session_state.pop("current-study", None)
                    st.session_state.pop("paper-processed-key", None)
                    st.toast("Workspace restored from the validated backup.")
                    st.rerun()
            except (ValueError, TypeError, KeyError) as exc:
                st.error(str(exc))
    with st.container(border=True, key="nq-panel-settings-2"):
        html(panel_title("Paper-account preferences", "No change here rewrites an existing trade's execution assumptions."))
        with st.form("workspace-preferences"):
            capital = st.number_input("Starting paper capital (₹)", min_value=1_000.0, max_value=100_000_000.0,
                                      value=float(ctx.workspace["ledger"]["initial_cash"]), step=1_000.0,
                                      disabled=bool(ctx.workspace["ledger"]["trades"]))
            auto = st.checkbox("Process new completed sessions when I open Paper trading", value=ctx.workspace["preferences"].get("auto_process", True))
            saved = st.form_submit_button("Save workspace preferences", disabled=bool(ctx.snapshot.get("is_demo")))
        if saved:
            ledger = ctx.workspace["ledger"] if ctx.workspace["ledger"]["trades"] else new_ledger(capital)
            ctx.save(ledger=ledger, preferences={**ctx.workspace["preferences"], "auto_process": auto})
            st.success("Preferences saved. Export a fresh backup to retain them.")
    with st.expander("Archive the current paper account and start clean"):
        st.warning("This preserves the current account in your private workspace archive and begins a new simulation. It is not a reconciliation of old returns. Download a complete backup first.")
        new_capital = st.number_input("New account capital (₹)", min_value=1_000.0, max_value=100_000_000.0, value=100_000.0, key="archive-new-capital")
        confirmation = st.text_input("Type ARCHIVE AND RESTART to confirm")
        backed_up = st.checkbox("I downloaded the current full private backup.", key="archive-confirm")
        if st.button("Archive & restart paper account", disabled=confirmation != "ARCHIVE AND RESTART" or not backed_up or bool(ctx.snapshot.get("is_demo"))):
            archive = deepcopy(ctx.workspace.get("archived_accounts", []))
            archive.append({"archived_at": datetime.now(timezone.utc).isoformat(), "ledger": deepcopy(ctx.workspace["ledger"])})
            ctx.save(ledger=new_ledger(new_capital), archived_accounts=archive)
            st.session_state.pop("paper-processed-key", None)
            st.rerun()
        st.caption(f"Archived corrected-engine accounts in this workspace: {len(ctx.workspace.get('archived_accounts', []))}. The supplied original ledger is in the separate legacy-private ZIP, not here or in validated returns.")


def data_settings(ctx):
    st.toggle("Explore synthetic preview data", key="demo-mode", help="An isolated demonstration workspace, never the live market snapshot or personal ledger.")
    if ctx.snapshot.get("is_demo"):
        st.warning("Synthetic preview is on. Disable it here to return to your personal workspace. None of these prices are live or historical market observations.")
    counts = coverage(ctx.snapshot)
    for col, values in zip(st.columns(3), [("Configured universe", str(len(ctx.registry.universe)), "Bundled Nifty 500 list; changes are explicit", "teal"),
                                         ("Currently analyzed", str(counts["analyzed"]), f"{counts['unassessed']} not currently assessed", "lime"),
                                         ("Price history", str(ctx.snapshot.get("history_sessions", 0)), "Maximum retained completed sessions per stock", "")]):
        with col:
            html(metric_card(*values))
    with st.container(border=True, key="nq-panel-settings-3"):
        html(panel_title("One snapshot, everywhere", "The screener, charts, portfolio marks and execution engine share this data version."))
        st.write(f"**Data as of:** {pretty_date(ctx.snapshot.get('as_of'))} · **Version:** `{ctx.snapshot['snapshot_id']}`")
        st.caption("The pipeline downloads three years with explicit adjustment/action options, calculates indicators, then retains up to 520 sessions. It does not append new bars to an indefinitely stale adjusted history.")
        st.caption("Freshness uses a conservative weekday/16:15 IST cutoff, not a verified exchange-holiday calendar. Weekday holidays can show stale/verify-session and block new paper orders. No incomplete current-day bars are accepted.")
        status_path = ROOT / "data/pipeline_status.json"
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text())
                st.caption(f"Last GitHub/local pipeline attempt: {status.get('attempted_at', 'unknown')}")
                if not status.get("success"):
                    st.error("Last pipeline attempt failed. The previous snapshot was retained. " + status.get("error", ""))
            except (ValueError, OSError):
                st.warning("Pipeline status file is unreadable. Check the workflow logs.")
        st.info("Recommended first refresh: GitHub → Actions → Daily Market Snapshot → Run workflow. Scheduled scans are opt-in so a private repository does not unexpectedly consume Actions minutes.")
        acknowledge = st.checkbox("Refresh all 500 instruments now. I understand this can take several minutes and may encounter provider rate limits.")
        if st.button("Refresh market snapshot now", type="primary", disabled=not acknowledge or bool(ctx.snapshot.get("is_demo"))):
            lock = refresh_lock()
            if not lock.acquire(blocking=False):
                st.warning("A market refresh is already running on this app host. Try again after it finishes.")
            else:
                progress = st.progress(0, text="Refreshing benchmark and completed daily history…")
                try:
                    snapshot = build_snapshot(ctx.registry, ctx.snapshot, lambda done, total: progress.progress(done / total, text=f"Refreshed {done} / {total} instruments"))
                    # Session-only override: no private state or app-host writes are
                    # assumed to synchronize back to the GitHub Actions checkout.
                    st.session_state["market-override"] = snapshot
                    st.toast("Market snapshot refreshed for this session.")
                    st.rerun()
                except Exception as exc:
                    st.error("Refresh did not replace the existing snapshot. " + str(exc))
                finally:
                    lock.release()
        if "market-override" in st.session_state:
            st.caption("You are viewing a session-refreshed snapshot. It is not published to GitHub and will not survive a session reset.")
            if st.button("Return to the repository snapshot"):
                st.session_state.pop("market-override", None)
                st.rerun()
    issues = [{"ticker": symbol, "quality": stock.get("quality", "Missing"), "data_as_of": stock.get("data_as_of", "Unavailable"), "error": stock.get("error", "")}
              for symbol, stock in ctx.snapshot.get("stocks", {}).items() if stock.get("quality") != "Current"]
    with st.expander(f"Coverage & refresh issues ({len(issues)})", expanded=bool(issues)):
        if issues:
            table(issues, [{"key": "ticker", "label": "Instrument"}, {"key": "quality", "label": "Quality"},
                           {"key": "data_as_of", "label": "Last session"}, {"key": "error", "label": "Details"}], "data-issues", ctx.dark)
        else:
            st.caption("No per-instrument issues in the loaded snapshot. An empty/uninitialized snapshot is not proof of complete coverage.")


def model_settings(ctx):
    cfg, execution = ctx.strategy, ctx.execution
    with st.form("model-settings"):
        html(panel_title("The six-rule model", "Default rules are preserved. These controls change thresholds, not the indicator definitions."))
        c1, c2, c3 = st.columns(3)
        watch = c1.number_input("Watchlist minimum conditions", min_value=0, max_value=6, value=cfg.watchlist_min_score, step=1)
        qualified = c2.number_input("Qualified minimum conditions", min_value=0, max_value=6, value=cfg.qualified_min_score, step=1)
        extension = c3.number_input("Maximum extension above 50 EMA (%)", min_value=0.0, max_value=100.0, value=cfg.max_pct_above_50ema * 100, step=1.0)
        st.divider()
        html(panel_title("Execution assumptions", "Long-only cash sizing; next-open entry; inclusive sessions; fees on actual filled notional."))
        c1, c2, c3 = st.columns(3)
        hold = c1.number_input("Hold sessions", 1, 252, execution.hold_sessions, step=1)
        atr = c2.number_input("ATR stop multiplier", .1, 20.0, float(execution.atr_multiplier), step=.1)
        cost = c3.number_input("Modeled round-trip fee (bps)", 0.0, 1000.0, float(execution.round_trip_cost_bps), step=1.0)
        c1, c2 = st.columns(2)
        entry_slip = c1.number_input("Entry slippage (bps)", 0.0, 1000.0, float(execution.entry_slippage_bps), step=1.0)
        exit_slip = c2.number_input("Exit slippage (bps)", 0.0, 1000.0, float(execution.exit_slippage_bps), step=1.0)
        submitted = st.form_submit_button("Save model settings", type="primary", disabled=bool(ctx.snapshot.get("is_demo")))
    if submitted:
        try:
            strategy = StrategyConfig(int(watch), int(qualified), extension / 100)
            execution = ExecutionConfig(int(hold), atr, entry_slip, exit_slip, cost)
            ctx.save(strategy=asdict(strategy), execution=asdict(execution))
            st.success("Saved. Existing paper positions retain their original parameters; future orders and studies use these settings.")
        except ValueError as exc:
            st.error(str(exc))
    st.info("These preferences re-evaluate the saved snapshot in your workspace. GitHub's public scan uses the checked-in defaults in src/config.py. The market-regime rule stays the original 200 EMA / three-session rule.")
    st.caption("One basis point is 0.01%. A 20 bps round-trip assumption charges 10 bps on entry notional and 10 bps on exit notional. This is a configurable research approximation, not a statutory tax/fee calculator.")


def learn(ctx):
    search = st.text_input("Search the guide", placeholder="Try ATR, freshness or backup…").casefold().strip()
    guide = {
        "The six conditions": "The score counts conditions met, not probability of success. A fresh 200 EMA breakout also satisfies above-200-EMA, so some conditions overlap. " + " ".join(note for title, note in RULES.values()),
        "EMA and market regime": "Stock EMAs use an initial-window simple-average seed, then exponential weighting. The Nifty regime retains the original adjust=False EWM rule, with a 200-observation warm-up. Three valid closes below that EMA classify Bearish; otherwise Bullish. Missing/short data is Unknown, and long setup classification pauses.",
        "RSI": "RSI compares smoothed gains and losses. This strategy awards one condition only when RSI is above 60 and at or below 70. It is not a price target. A flat series is explicitly defined as RSI 50 after warm-up.",
        "MACD": "The model uses 12/26 EMAs with a 9-session signal EMA. A condition requires a fresh crossover on the signal session, not merely a positive MACD. The signal timestamp matters.",
        "ATR and a provisional stop": "ATR smooths true ranges. The stop is entry minus the configured ATR multiple; the signal ATR is converted into the same provider price units as the entry. Position quantity is limited by both allocation and modeled stop risk, including fees. A gap can exceed that planned loss.",
        "Execution and costs": "An order is pending, not filled, when it is staged. It may enter the next observed session's open only if it was created before that open. The entry session counts as session one and is checked for stops. Gap stops use the weaker open; otherwise a touched stop uses its modeled level. Stop exits take priority over time exits.",
        "Corporate actions and revisions": "Indicators use the provider's Adj Close ratio; execution uses provider OHLC with auto_adjust=False. Yahoo history can already reflect split adjustments, so it is not an immutable point-in-time tape. Split events or changes to a processed bar freeze affected open positions for review. They are not silently revalued. Modeled dividends are credited on the ex-date to prior-session holders, without taxes/payment delay.",
        "Portfolio coverage": "Unpriced and trend-unassessed holdings remain explicit. Price P&L is computed only on holdings priced at the displayed snapshot date, compared with those same holdings' costs. Industry concentration uses invested cost. An EMA trend check is not a full portfolio risk assessment.",
        "Backtest versus account performance": "The research screen is a non-overlapping-per-ticker event study. Cross-ticker trades can overlap and independently reuse cash, so its mean returns cannot be presented as an account return. The paper account instead tracks cash, reserved allocations, actual quantities, fees and daily marked positions. Current constituents introduce survivorship bias into retrospective samples.",
        "Freshness and incomplete days": "Completed-bar cutoff is conservatively set to 16:15 IST on weekdays. This is not a verified NSE holiday calendar. Holidays or provider delays may block entries until verified/refreshed; stale or future/incomplete snapshots never silently become current. Chart month/year ranges are calendar offsets, not mislabeled row counts.",
        "Private backups and hosting": "The default workspace is session-scoped server memory, not a persistent database or login-protected vault. Export plain-JSON backups and keep them private. Local SQLite is opt-in for a trusted installation. App-host state and GitHub Actions state are separate; the market workflow never reads personal holdings or trades.",
    }
    matches = [(title, body) for title, body in guide.items() if search in (title + " " + body).casefold()]
    if not matches:
        st.info("No matching guide entry. Try a broader term.")
    for title, body in matches:
        with st.expander(title, expanded=bool(search)):
            st.write(body)
    st.caption("Nifty Quant Screener 2.0 · personal end-of-day research · no broker execution or investment recommendation.")
