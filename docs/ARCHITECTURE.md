# Architecture and maintenance

## Boundaries

```text
GitHub manual / opt-in weekday workflow
    → src.pipeline → yfinance daily observations
    → indicators + benchmark + quality checks
    → versioned market_snapshot.json.gz + summary + attempt status
    → explicit public-only Git commit

Streamlit app.py
    → load one public snapshot (cache keyed by file version / snapshot ID)
    → strategy service → signals
    → routed UI screen, shared theme/charts/selection component
    → personal Context → SessionStore (default) or LocalStore (opt-in)
    → explicit private download / restore

Paper trade submission → immutable assumptions + pending canonical order
    → shared execution.process_sessions → account events / positions / equity
Historical signal sample → same execution engine → independent event-study report
```

`app.py` owns routing, session mode and public-data caches. `ui/context.py` passes a workspace and its store to screens. Only the selected screen runs. Hidden screens do not download prices, parse uploads, process account events or run a study. The imports of screen modules themselves do not execute those actions.

The domain modules do not import Streamlit. `ui/theme.py` lazily imports it only when applying the theme, allowing pure rendering and domain tests without the full runtime.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `src/config.py` | Validated immutable strategy/execution parameters and reproducible model identity. |
| `src/instruments.py` | Canonical bare NSE identity, provider suffix conversion, exact company/ISIN lookup; no guessed tickers. |
| `src/indicators.py` | Explicit pandas indicator definitions, adjusted analysis series and raw-price execution units. |
| `src/screener.py` | Six conditions, eligibility gate, regime and pure literal filters. |
| `src/freshness.py` | IST completed-day cutoff and conservative weekday entry window. Not an exchange calendar. |
| `src/data_fetcher.py` | Explicit Yahoo request options, retries, validation and completed-day filtering. |
| `src/market.py` | Snapshot schema, compression, atomic file replacement and consistent signal conversion. |
| `src/pipeline.py` | Benchmark-first refresh, per-symbol failures, coverage and prior-good-snapshot retention. |
| `src/execution.py` | Order/account invariants, affordable fills, stops, session accounting, dividends and review events. |
| `src/paper_trader.py` | Personal-account adapter; no use in public GitHub market workflow. |
| `src/backtest.py` | Independent historical signal samples using the same execution policy. |
| `src/imports.py` | Single-read CSV/XLSX parsing, column mapping, validation and weighted consolidation. |
| `src/portfolio.py` | Matched valuation, cost-based coverage and concentration without filling unknowns with zero. |
| `src/storage.py` | Workspace schema, validated JSON envelope and session/SQLite persistence with revision checks. |
| `ui/screens/` | Six feature screens. Domain calculations remain outside presentation functions. |

## Public-data caching

Only public data is cached globally: the instrument registry, versioned snapshot, derived signals and synthetic fixture. Holdings, ledgers, upload contents and studies are not cached globally. The analysis cache includes the strategy settings and snapshot ID. The snapshot file cache key includes path, modification time and size. A selected stock is read from the same snapshot, not independently downloaded from a potentially different date.

The pipeline retains up to 520 sessions after computing indicators on the longer requested history. The constituent CSV is the original bundled list, not a claim that it is today's index membership. Historical studies are therefore explicitly subject to current-list selection/survivorship limitations. Failed constituent requests are reported; prior bars are not silently certified current.

The compressed snapshot is intentionally simple for a small personal deployment. Repeated binary snapshots grow Git history. Monitor repository size, provider rate limits and included Actions usage. Future long-lived deployments may need a different free-tier architecture or paid infrastructure, but this release does not assume either.

## Personal state and concurrency

Every mutation validates a workspace and advances its revision. SQLite saves use `WHERE revision = expected_revision`; session saves apply the equivalent check. Conflicts ask for a reload rather than overwriting. Backups also validate schema and ledger consistency. This is concurrency protection, not authentication.

Snapshot bar revisions and corporate actions can mark a paper trade `REVIEW_REQUIRED`. The account must not silently assert a fully priced equity curve through unresolved positions. Preserve an export and use the documented archive/restart path; no automatic reconstruction of legacy returns is attempted.

## UI design system

The references are interpreted through spacing, bento layouts, rounded panels, prominent typography and a limited palette—not by copying the reference images into the app. Both palettes live in `ui/theme.py`; shared responsive rules live in `assets/theme.css`. No custom font file, external image CDN, npm build or separate frontend is required.

Keyed Streamlit containers provide stable panel hooks. Per-session CSS and explicit Plotly/table colors implement the light/dark switch. This does not dynamically mutate Streamlit's process-wide theme configuration. Upgrading Streamlit can change widget markup, so run both theme checks and the real browser smoke script when changing the pin.

The small packaged HTML table is a Streamlit bidirectional component. It communicates selected **instrument IDs**, not sort-dependent row indexes; escapes values with `textContent`; supports keyboard selection; keeps horizontal scrolling inside the table; and resizes via the component message protocol. An accessible native selector is available alongside analysis. The preview and component test share the production assets.

## Adding a screen or provider

Keep service functions pure where possible; make data dates and missing observations explicit. Use the canonical instrument ID, the existing snapshot schema, and the shared execution engine rather than adding a second price loader or simulator. Add domain tests, a Streamlit AppTest route and browser smoke coverage. Never put personal data into market-workflow outputs.

See [Methodology](METHODOLOGY.md), [Storage and privacy](STORAGE_AND_PRIVACY.md) and [Validation](VALIDATION.md) for the applicable limitations.
