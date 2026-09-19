# Storage, backup and privacy

## The chosen personal-use architecture

There is no app-level sign-in, external database, paid API or broker connection. The public-data pipeline and the personal workspace are deliberately separate. This is **not** an authenticated multiuser product.

| Information | Default location | Sent to the GitHub worker? |
|---|---|---|
| Universe, instrument registry, public market observations | Repository / app's read-only checkout; explicit session refresh can override it | Yes, public market outputs only |
| Holdings, watchlist, filters, paper account, model settings, studies | The current Streamlit session on the app server | No |
| Downloaded full workspace backup | The device/location you choose | No, unless you upload it yourself |
| Opt-in local SQLite workspace | `.local/workspace.sqlite3` or the configured path | No |
| Legacy original ledger | Separately supplied private archive | Never intentionally |

Session data is processed on the server; it is not encrypted client-only storage. The host/operator controls the runtime. Session separation is not user authentication or a security boundary for an untrusted operator.

## Session mode: the default

`NIFTY_STORAGE=session` keeps personal state in `st.session_state`. It does not deliberately write your holdings or ledger to the repository. The data can disappear on reload, a lost/replaced WebSocket, restart or redeploy. Streamlit documents that Session State is tied to the WebSocket and that reload resets it.[1]

**After personal changes, download a full private workspace backup.** This is the persistence mechanism for the default no-external-service hosted setup. Keep it somewhere private, with your device's own backup/encryption protection. A CSV holdings export is useful for interoperability, but is not a full workspace backup.

To restore: Settings → Workspace → upload the version-2 JSON → review and explicitly restore. The checksum, schema, numeric fields and account consistency are validated before replacement. The SHA-256 checksum detects accidental changes; it is **not a signature**, authenticity check or encryption. A person who edits a file can recompute the checksum. Only restore files you trust.

A backup includes holdings, the complete corrected ledger, watchlist, saved filters, settings, stored studies and any archived corrected accounts. It does not include all market snapshots. The standalone legacy archive is not accepted as a validated version-2 workspace.

## Optional local mode

For your own trusted computer or a genuinely access-controlled single-user installation:

```dotenv
NIFTY_STORAGE=local
NIFTY_DB_PATH=.local/workspace.sqlite3
```

SQLite uses transactions, WAL and revision checks so an outdated action cannot silently overwrite a newer workspace. A corrupt database produces an error rather than a silent reset. Stop the app and preserve the original damaged database before troubleshooting; point the app at a new path and restore a known-good JSON backup.

Local mode is **one shared workspace**, not one account per browser. Do not enable it on a public/shared app. A database file on a disposable host is not a durable cloud database. Independent downloaded backups remain necessary. Ignore rules reduce accidental publication of local files; they do not protect files already tracked in Git or older commits.

## Workflow isolation and refresh behavior

The GitHub workflow reads the stock universe and Yahoo observations, then stages only these public outputs:

- `data/market_snapshot.json.gz`
- `data/latest_screener_results.json`
- `data/pipeline_status.json`

It does not read or execute a personal paper account. The old double invocation of the paper trader is removed. Opening Paper trading can process new completed sessions in your current workspace; alternatively use its explicit process button. No private data is pushed back to GitHub, and no private background worker runs after you close the app.

The Settings refresh downloads public data into the current session. It is not a repository commit and does not survive a session reset. A GitHub refresh becomes available after the app host updates its checkout/restarts as appropriate. Always check the displayed snapshot date, rather than assuming an update occurred.

## Demo isolation

Synthetic preview data and its workspace have separate session keys. Importing holdings and submitting paper orders are disabled in demo mode. Switching the preview off returns to the personal workspace. The preview does not manufacture validated historical trading results.

## Before making a repository public

Do not upload the separate legacy-private ZIP, original project ZIP, personal backups, holdings, local databases, actual `.env`, deployment secrets or downloaded broker statements. Run `python scripts/verify_repository.py` after staging the intended changes. The guard checks the current publishing tree/Git index for known risky files and credential patterns; it is not a comprehensive security scanner.

Existing tracked private files must be explicitly removed; `.gitignore` does not erase their history. An entirely new clean repository is a simple option for this release, but does not remove data already published elsewhere. Review older commits and rotate any exposed credentials. Deployment visibility must be configured independently from source-repository visibility.[2]

## Deliberately deferred

Before a multiuser release, add real authentication, per-owner authorization, durable shared storage, migrations, deletion/export controls, server-side abuse controls and a threat review. The separated repository/service interfaces make that migration easier, but do not implement those protections now.

## References

1. [Streamlit Session State caveats](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state#caveats-and-limitations).
2. [Streamlit Community Cloud app settings and access](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings).
