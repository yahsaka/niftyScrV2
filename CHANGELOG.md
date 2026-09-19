# Changelog

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
