# Validation report

## What actually ran in the preparation environment

| Check | Observed result | Scope |
|---|---|---|
| Python compile check | Passed | `app.py`, `src`, `ui`, scripts and tests compile. This is not runtime integration. |
| Pytest | **111 passed, 1 skipped** | Actual domain/service tests. One Streamlit integration module was skipped because the real dependency was unavailable. No replacement Streamlit module or fail-fast import placeholders were used in these new tests. |
| Chromium shared-preview/component checks | **12 checks passed** | Production HTML table, shared cards/CSS/Plotly preview, not a running Streamlit server. |
| Publishing guard | Passed | No known private publishing files, credential patterns or font binaries in the new source tree. Not a comprehensive secrets scan or a history audit. |

The local Python interpreter was **3.13.5**, with pandas **2.2.3**, NumPy **2.3.5**, Plotly **6.5.2**, pytest **9.0.2** and Playwright **1.57.0**. The delivered deployment target is **Python 3.12**, with direct dependencies pinned in the requirements files (including NumPy 2.2.6). Therefore these local results do not certify the complete pinned deployment environment.

Machine-readable records are in [validation/core-tests.xml](validation/core-tests.xml) and [validation/components.json](validation/components.json).

## What the core tests cover

Execution tests cover repeated processing, incremental versus batch outcomes, entry-day stops, gap stops, inclusive holding counts, pending reservations, cash affordability, identical shared engine behavior, immutable order assumptions, chronological cash/P&L, dividend events, missing bars, revised bars, splits and account validation. The hardening cases include missing bars after a position already closed, impossible recorded holding periods and corrected closed-account cash reconciliation.

Import/storage tests cover consumed upload streams, CSV/header aliases and preambles, XLSX parsing, exact instruments, rejected unknown names and nonfinite/invalid quantities, weighted duplicates, malformed/checksum-invalid backups, demo separation, session conflicts, local SQLite transactions and corruption. Portfolio cases distinguish missing/invalid prices from zero market value.

Market/strategy tests cover explicit indicator boundaries, the strict 2× volume rule, adjusted/raw units, regime and eligibility behavior, literal search, calendar ranges, completed-day freshness, snapshot round-trips and a fake-provider pipeline with retained failures. Historical original regression scenarios are retained and adapted to explicit corrected fee accounting.

These are synthetic deterministic cases, not empirical proof of investment returns or a guarantee against all defects.

## What the 12 browser checks cover

The browser loaded the actual `ui/components/select_table/index.html` and the self-contained preview built from production shared assets. Checks include light/dark desktop views, tablet/mobile page containment, preview navigation and real Plotly figures, all six rule rows visible, text escaping, numeric sorting, keyboard-selected instrument IDs, parent selection synchronization, dark table palette, frame resizing/contained scrolling and an empty table state. Related assertions are grouped into 12 named checks in the JSON report.

Preview viewports were 1440×1080, 768×1024 and 390×844, plus a 320-pixel-wide isolated table. PNGs under `docs/previews/` are screenshots of this **synthetic shared-component preview**, not screenshots of a fully running Streamlit application. A short manual visual inspection checked labels, card clipping, theme colors and table boundaries. A complete accessibility audit, assistive-technology test or every-device check was not performed.

## What did not run locally

The environment could not install missing Streamlit/yfinance/pyarrow/tenacity runtime dependencies because package/network access failed. Consequently:

- The real Streamlit AppTest module (15 parameterized cases) did **not** execute locally.
- The full Streamlit browser smoke test and its native widget/iframe-to-Python interaction did **not** execute locally.
- A live Yahoo 500-stock refresh, actual market/provider data validation, GitHub scheduling/push and hosted redeployment did **not** execute locally.

There are no claims of having deployed to the user's GitHub account or host. The screenshots and isolated component checks do not substitute for those checks.

## Deployment verification supplied in the repository

**Actions → Product tests** installs the pinned runtime on Python 3.12, compiles the code, runs the full pytest suite and publishing guard, installs Chromium, tests the shipped component/preview, then launches real Streamlit in isolated synthetic mode and runs `scripts/browser_smoke.py`.

The AppTest module covers six empty routes, six synthetic routes, two theme/detail cases and the Settings sections. The full browser script checks route changes, a literal `[` no-match search, reset, table-to-analysis interaction, theme switching and responsive page containment. These scripts are provided to execute on GitHub; their presence is not a passed result. Resolve any failures before relying on the app.

Next, run **Actions → Daily Market Snapshot** manually and inspect data date, per-instrument coverage and refresh status. Verify host visibility separately. Import a small known holdings file, check matched values, make/download/restore a test workspace backup, and test your target devices before entering a larger personal account.

## Reproduce locally after installing dependencies

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q app.py src ui scripts tests
python -m pytest -q
python scripts/verify_repository.py
python -m playwright install chromium
python scripts/build_preview.py
python scripts/component_checks.py
```

For the real browser checks, start the actual app in a separate terminal:

```bash
# macOS/Linux; on Windows set the environment variable in PowerShell instead.
NIFTY_DEMO=1 streamlit run app.py
# In another terminal:
python scripts/browser_smoke.py --url http://localhost:8501
```

Keep browser diagnostics and all personal exports out of public source commits. The automatic browser checks use synthetic data only.
