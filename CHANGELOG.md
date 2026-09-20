# Changelog

## UI correctness pass — 2026-09-20

Verified against the real Streamlit 1.55 runtime in a headless browser (light and dark,
at 1440 / 1024 / 768 / 390 px), not against the static `docs/preview.html` mock. The
previous polish pass introduced rules whose selectors either lost specificity battles or
targeted test IDs Streamlit 1.55 does not emit; those regressions are corrected here.

- **Fixed unreadable text on tinted cards.** A blanket `.nq-card-foot{color:var(--muted)!important}`
  overrode the teal/lime/purple foot colours, measuring **1.5:1** contrast on the teal regime card
  (light) and the lime metric card (dark). The muted rule is now scoped to neutral surfaces only;
  tinted cards measure **5.6:1 / 6.6:1** (WCAG AA).
- **Fixed invisible primary buttons.** `st.download_button(type="primary")` lost its background to
  the more specific `[data-testid="stDownloadButton"] button` rule, and `st.form_submit_button`
  emits `kind="primaryFormSubmit"`, which `button[kind="primary"]` never matched. Both rendered
  mint text on a white button ("Download full private workspace backup", "Stage next-open paper
  order"). Primary selectors are now paired with their containers, and hover states added.
- **Fixed illegible disabled buttons.** Disabled actions no longer rely on `opacity:.45` over a
  forced light label; they use an explicit soft surface with muted text.
- **Fixed unthemed alerts and toasts.** Theming targeted `stAlert`, but the painted surface is the
  child `stAlertContainer`, so every `st.info`/`warning`/`error`/`success` kept Streamlit's default
  blue or yellow inside a teal palette. Alerts now use the design tokens with a per-severity left accent.
- **Fixed the dark-mode toggle label wrapping on mobile.** Two rules targeted `[data-testid="stToggle"]`;
  `st.toggle` renders under `stCheckbox` in 1.55, so the intended `white-space:nowrap` never applied.
- **Aligned the Screener filter row.** The text input, select and slider no longer drift off a shared
  baseline, and the slider caption sits with its control.
- **Added a scroll affordance to the results table.** The final row was clipped mid-height at
  `max_height` with no indication more rows existed; a fade now appears only while the table is
  scrollable and clears at the end of the list.
- **Equalised card heights** in 4-up metric rows so a wrapping foot no longer staggers the row.

## UI polish follow-up — 2026-09-19

- Switched application, Plotly charts and the custom results table to Google Roboto with system fallbacks.
- Fixed dark text on teal active navigation, segmented controls and primary actions.
- Increased secondary-text contrast in light and dark themes.
- Displayed snapshot refresh time in IST in the user-facing status strip.
- Added the common data-status strip to Settings and aligned Backtest page naming with navigation.
- Fixed Portfolio cost-weight and Backtest sensitivity percentage formatting.
- Standardized card currency formatting to Indian digit grouping.
- Exported the user-facing “Qualified” label instead of internal “Trade-Ready”.
- Reduced the visual prominence of the manual Screener selector while preserving a keyboard fallback.
- Moved Paper-trading backup into a page-level action and reduced oversized empty states.
- Improved mobile topbar spacing, toggle wrapping, 3×2 navigation balance and sticky first columns in horizontally scrollable tables.
- Preserved the duplicate Streamlit navigation-key fix and the Playwright visible-label toggle fix.


## Personal workspace redesign — schema version 2

### Correctness and data

- Replaced separate paper/backtest fill logic with one deterministic next-session engine.
- Fixed repeated session counting, same-day stop evaluation, schema mismatch and cost/cash inconsistencies.
- Added pending/open/closed/cancelled/review states, immutable saved assumptions, reservations, audit events and marked account equity.
- Replaced summed trade percentages with either actual account accounting or explicitly independent event-study statistics.
- Made sizing cash-constrained, including estimated fees, without presenting stop risk as a guaranteed loss limit.
- Fixed consumed-stream portfolio uploads; added mapping, exact identifiers and rejected-row review.
- Unified snapshot data across screening, charts, holdings and simulation. Added explicit freshness, refresh failures and coverage.
- Preserved the six conditions, score thresholds, original bundled universe and Yahoo provider. The volume condition remains strictly above twice the 20-session mean; the 15% extension exclusion remains separate.
- Made indicator math explicit and reproducible instead of depending on whichever optional backend happened to be installed.

### Experience

- Redesigned all six screens around light/dark sage-and-teal bento layouts with lime accents.
- Added sortable row-to-analysis selection, literal search, saved views, watchlist and clear no-match states.
- Reduced chart density through optional supporting indicators and calendar-based ranges.
- Added portfolio matched P&L/concentration and separate analyzed coverage.
- Added model documentation, editable assumptions, private workspace backup/restore and isolated synthetic preview.

### Operations and migration

- Defaulted personal data to session scope; added optional trusted-local transactional SQLite.
- Removed personal ledger processing from GitHub. Only public snapshot/status files are staged.
- Made recurring scans opt-in; retired the keep-awake workflow.
- Pinned direct dependencies, declared dotenv explicitly and supplied tests plus browser checks.
- Delivered the original project/ledger separately as a private unvalidated archive. No old trade is silently converted to validated performance.
- Replaced the monolithic application with domain services and routed screens.

### Not included

Authenticated multiuser use, live broker execution, intraday guarantees, durable hosted personal storage, an official exchange holiday calendar, pooled historical portfolio optimization and automatic corporate-action/legacy-account reconciliation remain outside this personal no-paid-service release.

### Verification boundary

See [Validation](docs/VALIDATION.md). Domain checks and the shared-component visual checks ran in the preparation environment. Real Streamlit integration/browser and live Yahoo refresh checks require the supplied deployment/CI environment; they are not represented as locally passed.
