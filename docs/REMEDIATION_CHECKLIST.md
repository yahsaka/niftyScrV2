# Audit remediation map

This maps the earlier product review to the delivered implementation. “Implemented” means code is present; validation scope is recorded separately in [Validation](VALIDATION.md).

| Earlier finding | Implemented change | Main location / test |
|---|---|---|
| Duplicate paper-processing sessions | Last processed session + event identity; deterministic replay; workflow no longer touches personal trades | `execution.py`, `test_execution.py` |
| Inconsistent UI/worker/backtest records | Canonical version-2 account and shared execution adapter | `execution.py`, `paper_trader.py`, `backtest.py` |
| Entry-day stop not checked | Stop rules applied on entry session, gap-aware on later sessions | `test_execution.py`, original regression tests |
| CSV read twice | Bytes read once; CSV/XLSX preview and mapping | `imports.py`, `test_imports_storage.py` |
| `.NS`/bare symbol mismatch | One canonical registry identity throughout | `instruments.py`, import and market tests |
| Guessed company names | Exact lookup or explicit rejected/manual review | `imports.py` |
| Indefinitely old stock cache | Versioned shared snapshot; refresh/freshness/quality state | `market.py`, `pipeline.py`, market tests |
| Unknown holdings shown as healthy | Separate price/trend assessment and cost-weighted coverage | `portfolio.py`, hardening tests |
| Summed trade percentages called strategy return | True personal-account cash/equity; separately labeled event study | `execution.py`, `backtest.py` |
| Risk-only quantity could exceed cash | Min of risk-based and fee-inclusive affordable quantity | `execution.py`, execution tests |
| Shared JSON ledger and mismatched deployments | Default session workspace; private export; opt-in local SQLite; public-only worker | `storage.py`, storage tests |
| Search regex crash | Literal substring filtering | `screener.py`, market tests |
| Empty filters reverted to all stocks | Explicit empty screen, no hidden fallback | `ui/screens/screener.py`, AppTest + browser script |
| Table disconnected from analysis | ID-based selection bridge and native accessible selector | packaged table, component checks |
| Dense charts and distant action | Compact primary chart; optional indicators; adjacent assumptions/action | UI screens/charts |
| “3M/6M/1Y” actually row counts | Calendar offsets | `ui/charts.py`, market tests |
| Hidden tabs executing work | Routed screens | `app.py` |
| Unpinned / implicit dependencies | Exact direct pins, explicit dotenv, target Python 3.12 | requirements files/workflows |
| Personal old data in publishing tree | Separate private archive, clean start, repository guard | migration guide/scripts |

## Explicit limits rather than silent assumptions

- Holiday handling is conservative weekday logic, not a maintained exchange calendar. It can block a legitimate holiday-adjacent order.
- Corporate splits/revised processed bars trigger review; they are not automatically reconstructed.
- Hosted default personal persistence requires downloads/restores; no free external database is assumed.
- The stock universe is preserved, not automatically updated to current membership.
- Historical samples use the retained snapshot window and do not recreate a point-in-time constituent database.
- No notifications, new prediction model, live orders or authenticated users were added merely to increase feature count.
