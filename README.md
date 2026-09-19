# Nifty Quant Screener

**A personal, end-of-day research workspace for the bundled NSE stock universe.**

Find technical setups, inspect the six conditions behind them, analyze imported holdings, and run a cash-only paper account or historical event study. This release keeps Streamlit, the existing constituent list, Yahoo Finance through yfinance, and GitHub workflows. It adds no paid API, external database, authentication service, or broker integration.

> **Start here:** [Upload and deploy](UPLOAD_TO_GITHUB.md). The deliverable is a complete replacement repository, not a patch. Keep the separately supplied legacy-private archive **off GitHub**.

## What changed

| Area | This release |
|---|---|
| Execution | One next-open execution engine shared by paper trading and historical simulations; entry-day stops, gap handling, explicit fees, inclusive session counts and repeat-safe processing. |
| Paper account | Canonical pending/open/closed records, cash reservations, affordable quantities, cost-based P&L, marked equity, dividend events, review guards and an audit trail. |
| Imports | Single-read CSV/XLSX parsing, header detection, column mapping, exact instrument matching, rejected-row review and weighted duplicate merging. |
| Data | One versioned snapshot for all features; data date, refresh time, coverage and failures remain visible. No chart-triggered network calls or indefinitely stale local caches. |
| Research | Literal search, industry/condition filters, saved views, watchlist, row-to-analysis selection, honest empty states, calendar chart ranges and configurable assumptions. |
| Portfolio | Invested cost, matched current value/P&L, concentration, and separate price/trend coverage. Unassessed holdings never become “healthy.” |
| Interface | Light/dark toggle; sage, teal and lime palette; rounded cards; compact analysis views; theme-aware charts and accessible, sortable tables. |
| Privacy | Session-scoped personal state by default; JSON backup/restore; optional local SQLite on a trusted installation. GitHub processes market data only. |

The score is a count of conditions, **not calibrated confidence, a probability of profit or an investment recommendation**.

## Run locally

Use **Python 3.12** for the pinned deployment target.

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

No secret is required for the default session setup. The application starts with genuine empty states, **not example market prices**. For the first market snapshot, use GitHub's **Daily Market Snapshot → Run workflow**, or run:

```bash
python -m src.pipeline
```

The full 500-instrument refresh can take several minutes and depends on provider availability. Settings → Data & refresh also offers an explicit refresh, but that version is session-only and is not pushed to GitHub.

To explore the UI without network access after installing dependencies, enable **Settings → Data & refresh → Explore synthetic preview data**. Its separate, clearly labeled workspace cannot import personal holdings or create paper orders. Generated fixture values are not historical market evidence.

## Personal data: read before use

**Session mode is not persistent storage.** Export **Settings → Workspace → Download full private workspace backup** after personal changes and before a browser reload, disconnect, restart or redeploy. Restore the JSON in the next session. Downloaded backups contain personal information and are not encrypted. Streamlit documents that session state is tied to the WebSocket and can reset on reload.[1]

For your own trusted computer, copy `.env.example` to `.env` and set:

```dotenv
NIFTY_STORAGE=local
NIFTY_DB_PATH=.local/workspace.sqlite3
```

This uses transactional SQLite, without a paid service. **Do not enable local mode on a publicly accessible/shared deployment:** there is one shared workspace and no app-level login. A free-host filesystem is not a durability guarantee. Keep independent backups even when local storage is enabled. See [Storage and privacy](docs/STORAGE_AND_PRIVACY.md).

The GitHub worker never reads your holdings or paper account. It publishes market observations. Pending personal orders catch up through completed sessions when you open Paper trading (when enabled) or press **Process completed sessions**. There is no unattended private-account synchronization between GitHub and an app host.

## Deploy without adding paid services

The workflow and app are designed for a no-paid-service setup, **not a guarantee of unlimited free infrastructure**. Streamlit Community Cloud is an available deployment option.[2] GitHub's standard hosted Actions runners are free for public repositories; private repositories have plan-dependent included usage and possible charges beyond it.[3]

Scheduled scans are opt-in. First run the workflow manually. To enable the checked-in weekday schedule, add the repository **Actions variable** `RUN_SCHEDULED_SCANS` with value `true`. The workflow requests 16:45 IST on weekdays; schedules can be delayed or disabled by GitHub and are not an exchange calendar.[4] Do not configure an unnecessary keep-awake service. The old ping workflow is deliberately retired.

Set an appropriate Actions budget/spending limit and check your account's current allowances before enabling recurring runs. The app has no paid-service credentials or automatic purchase path. The code's no-cost design does not waive provider terms or hosting limits.

## Research model

The six-rule strategy and default thresholds are preserved: above 200 EMA, fresh 200 EMA breakout, above 50 EMA, RSI in `(60, 70]`, volume strictly above 2× its 20-session mean, and fresh MACD crossover. A separate eligibility gate excludes prices more than 15% above the 50 EMA by default. Watchlist begins at 3 conditions; Qualified begins at 5. A bearish or unknown benchmark regime suspends classification. Definitions are explicit in `src/config.py`, `src/indicators.py` and `src/screener.py`.

The corrected fee accounting and fixed indicator implementation can change outputs compared with the original unpinned environment. Existing trades retain their saved assumptions. Details, known limitations, conservative holiday handling and the distinction between an event study and a portfolio are in [Methodology](docs/METHODOLOGY.md).

**No live broker orders, intraday promises, authenticated multiuser accounts, exchange-grade point-in-time data or automatic corporate-action reconciliation are included.** A review-required account can be preserved and archived before restarting; this does not validate or repair its old returns.

## Project layout

```text
app.py                       Streamlit entry point; routed screens and session theme
src/                         Strategy, execution, imports, storage and market services
ui/screens/                  Overview, Screener, Portfolio, Paper trading, Backtest, Settings
ui/components/select_table/  Dependency-free, bidirectional accessible HTML table
assets/theme.css             Responsive design system
.github/workflows/           Public market refresh and product checks
scripts/                     Browser checks, preview builder and repository safety checks
examples/                    Non-personal import template
data/nifty500_tickers.csv     Original configured stock universe
EQUITY_L.csv                 Original additional identifier registry
requirements*.txt            Direct dependency pins
UPLOAD_TO_GITHUB.md           Deployment and migration instructions
docs/                        Architecture, storage, methodology and validation notes
```

## Tests and visual preview

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/verify_repository.py
python -m playwright install chromium
python scripts/component_checks.py
```

The **Product tests** workflow also runs real Streamlit AppTest cases and a real app browser smoke script. Read [Validation](docs/VALIDATION.md) for the exact checks run in the preparation environment and what could not be executed there. Direct dependencies are pinned; this is not a hash-locked transitive dependency tree.

`docs/preview.html` is an optional, self-contained **synthetic design preview** built from shared production cards, charts and the table component. It supports a theme switch and two preview screens. It is **not** the deployed application or evidence that all Streamlit widgets were browser-tested. Rebuild with `python scripts/build_preview.py`; launch the actual app with `streamlit run app.py`.

## References

1. [Streamlit Session State caveats](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state#caveats-and-limitations).
2. [Streamlit Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app).
3. [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
4. [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
5. [yfinance download API and options](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html). Check the upstream project and provider's terms for your intended use; this app makes no redistribution or service-level guarantee.
