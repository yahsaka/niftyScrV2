# Nifty Quant Screener — UI polish patch

This patch is intended for the already-deployed `niftyScrV2` repository. It contains **code/UI files only** and deliberately does not contain `data/`, personal workspace files, or market snapshots.

## What it fixes

- Loads Google **Roboto** for the Streamlit UI and custom results table, with system-font fallbacks if Google Fonts is unavailable.
- Uses Roboto in Plotly chart typography as well.
- Fixes dark text on teal active navigation, segmented controls and primary buttons.
- Increases muted/help-text contrast in light and dark themes.
- Improves the mobile top bar, prevents the Dark mode label from wrapping, gives the Streamlit toolbar breathing room, and balances navigation into three items per row where the DOM allows it.
- Keeps the first table column sticky on narrow screens while the rest scrolls horizontally.
- Displays refresh timestamps in IST instead of UTC in the user-facing status strip.
- Adds the common snapshot/source/freshness strip to Settings.
- Renames the Backtest page eyebrow from “Historical research” to “Backtest”.
- Fixes Portfolio `Cost weight` to display as a percentage.
- Fixes Backtest fee-sensitivity `Positive-return share` to display as a percentage.
- Uses Indian digit grouping in app-level rupee values (`₹1,00,000`, `₹12,34,567.50`).
- Exports the user-facing setup status `Qualified` instead of internal `Trade-Ready`.
- Moves the Screener manual stock selector into a collapsed keyboard-fallback expander; row selection remains primary.
- Moves the Paper-trading workspace backup to a clearer page-level action.
- Removes misleading arrow-in-circle decoration from non-action metric cards; semantically requested icons remain.
- Reduces oversized empty-state height.
- Preserves the fixed Streamlit navigation container key (`navigation-shell`).
- Preserves the Playwright theme-toggle fix that clicks the visible Streamlit toggle label.
- Adds UI-regression tests.

## Upload / replace

Replace the files in your GitHub repository with the files from this patch **using the same paths**. Do not move nested files to the repository root.

You do **not** need to touch anything in `data/` for this patch.

After committing the replacement files:

1. Open **GitHub → Actions → Product tests**.
2. Let the automatic run finish, or manually run it on `main`.
3. Confirm the workflow is green.
4. Streamlit Community Cloud should redeploy the app automatically from the new commit.
5. Hard-refresh the deployed app and check Overview + Screener in light/dark and mobile widths.

A fresh **Daily Market Snapshot is not required** for this UI-only patch unless you separately want newer market data.

## Validation performed before packaging

- `python -m compileall`: passed.
- Domain/unit tests: **116 passed**, with the real-Streamlit AppTest module skipped in this preparation environment because Streamlit is not installed here.
- Shared preview/custom-component Chromium checks: **12 passed** using system Chromium.
- The GitHub CI workflow remains the authoritative check for real Streamlit integration and the live browser smoke suite.

## Google Fonts note

Roboto is requested from Google Fonts at runtime. If that request is blocked or offline, the UI falls back to the local system sans-serif stack instead of failing.
