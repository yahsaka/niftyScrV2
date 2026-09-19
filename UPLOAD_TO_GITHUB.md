# Upload to GitHub and launch

## 1. Choose the correct archive

Use **`nifty-quant-screener-github-ready.zip`** for the application. Extract it on your computer.

Do **not** upload `nifty-legacy-private-DO-NOT-UPLOAD.zip`, personal backups, account databases, broker statements or the original project ZIP. The separate private archive preserves the original project and unvalidated ledger unchanged. It is for your private records, not a second deployment folder.

## 2. Upload the repository contents

A **new repository** is the least ambiguous way to publish this replacement without carrying forward old personal records or workflows. Choose public/private visibility deliberately; private source visibility is not the same thing as application access control.

In GitHub, create the repository, then use **Add file → Upload files** and upload the extracted **contents**, not the ZIP or an extra enclosing folder. At repository root you should see:

```text
app.py
requirements.txt
README.md
UPLOAD_TO_GITHUB.md
src/
ui/
assets/
data/
examples/
scripts/
tests/
docs/
.github/workflows/
.streamlit/config.toml
.env.example
.gitignore
.python-version
runtime.txt
EQUITY_L.csv
```

**Include the hidden `.github` and `.streamlit` folders.** Without them you will lose automation or app configuration. File managers may require “Show hidden files.” GitHub Desktop or Git is usually easier for preserving the complete directory tree than multiple browser-upload batches. The archive does not contain installed dependencies, font files, credentials, personal ledgers, or a fabricated current market snapshot.

Using Git instead of browser upload is optional:

```bash
# Run from the extracted repository directory, not its parent.
git init
git add .
git status --short
# Inspect this list: there must be no personal backup, .env or SQLite database.
git commit -m "Rebuild Nifty Quant Screener: reliability and dual-theme UI"
git branch -M main
git remote add origin YOUR_REPOSITORY_GIT_URL
git push -u origin main
```

### Updating an existing repository instead

Treat this as a **complete replacement**, while keeping the repository's `.git` directory only when using Git locally. Do not overlay it and assume obsolete files disappeared. Disable the old scheduled jobs before migration and retain a private backup.

Delete any tracked `data/paper_trades.json`, personal holdings, backtest history, obsolete caches and obsolete workflows from the published working tree. The provided `daily_screener.yaml`, `run_tests.yaml` and `ping_url.yaml` replace the three existing workflow filenames. Check for additional old workflows you created separately. The app never imports the old ledger into the corrected account.

**Adding `.gitignore` does not remove already tracked files or erase Git history.** Deleting a personal file now does not remove it from earlier commits. A new clean repository avoids copying that old history, but does not erase the old repository. Review the old repository's visibility, copies and history separately. GitHub provides [sensitive-data removal guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository). Rotate any exposed credentials rather than merely deleting the file.

For a local working-tree archive before removal:

```bash
python scripts/archive_legacy.py --source data/paper_trades.json
# The utility copies and verifies first. Deletion requires a separate explicit flag:
python scripts/archive_legacy.py --source data/paper_trades.json --remove-working-copy
```

Its ignored `.local/legacy-unvalidated` output is also private. It does not rewrite Git history.

## 3. Run the checks and first scan

Open **Actions → Product tests → Run workflow**. Resolve any failed installation, test or browser checks before relying on the application. The delivery environment could not install Streamlit; these real integration checks are included for this deployment verification rather than represented as already passed.

Open **Actions → Daily Market Snapshot → Run workflow** on the deployed branch. This downloads the market data and commits only these outputs:

```text
data/market_snapshot.json.gz
data/latest_screener_results.json
data/pipeline_status.json
```

The workflow requests `contents: write` for that purpose and uses the built-in `GITHUB_TOKEN`; no personal access token is required by this project. Repository/organization policy or branch protection can restrict the push. Check **Settings → Actions → General → Workflow permissions** and your branch policy when a push fails. Do not weaken unrelated protection rules without understanding them; a permitted automation branch or manual local scan is another deployment choice.

Provider errors are reported in workflow logs/status. A failed benchmark refresh does not replace a prior valid snapshot. Partial stock coverage is explicit. “Workflow completed” does not mean every instrument was covered.

## 4. Deploy the Streamlit application

On Streamlit Community Cloud, create an app from the GitHub repository and choose:

| Setting | Value |
|---|---|
| Repository | Your new/replacement repository |
| Branch | The branch containing the uploaded files, normally `main` |
| Main file path | `app.py` |
| Python | **3.12**, selected in deployment advanced settings |
| Secrets | None for the default session setup |

Keep `NIFTY_STORAGE=session`, the default. Do not enable the single-workspace local SQLite mode on a shared/public host. No application-level sign-in is implemented. Configure host-level app visibility for personal use, and verify it separately from repository visibility. Community Cloud documents [deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app) and [app settings/access](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings).

The normal first page can be empty until the market workflow succeeds. This is intentional. Preview the styling through **Settings → Data & refresh → Explore synthetic preview data**; switch it off before using market results.

## 5. Enable scheduled scans deliberately

Under repository **Settings → Secrets and variables → Actions → Variables**, add:

```text
RUN_SCHEDULED_SCANS = true
```

This is a repository variable, not a secret. The checked-in schedule is weekdays at 11:15 UTC / 16:45 IST. It is not an exchange-holiday calendar or a guarantee of exact execution time. Set account spending controls and verify private-repository usage allowances first. Keeping the variable absent/false leaves the job manual-only. The old keep-awake ping is disabled.

The public snapshot is a rolling history, but every committed binary version remains in Git history. Monitor repository size over time. Reducing `--sessions` below the default 520 (minimum 220) trades away backtest and catch-up history; it is not a cost-free storage optimization for existing accounts.

## 6. First personal-use checklist

- Confirm that the app's data date and coverage are acceptable; inspect failures rather than treating unknown holdings as healthy.
- Import a small CSV/XLSX through Portfolio and check the mapping and quantities before committing it. The example CSV is only a format template.
- Set initial paper capital and assumptions in Settings. Stage orders only from qualified, fresh setups during the permitted pre-next-open window. No broker order is sent.
- Download a **full private workspace backup** after personal changes. Session memory can reset on browser reload, disconnect, app restart or redeployment. Restore the backup in Settings next time.
- Test both themes on your target devices. `docs/VALIDATION.md` identifies the locally verified core/components and the unverified full-runtime checks.

## Common issues

**“No snapshot”** — run the market workflow; confirm its commit reached the deployed branch. A synthetic preview is never substituted automatically.

**Prices look stale after a manual app refresh** — Settings reports whether you are viewing a session override. Return to the repository snapshot when the workflow's newer version is deployed.

**An order cannot be staged** — check qualification, freshness, next-session opening time, available cash, duplicate ticker/session orders and data-review warnings. The model intentionally does not pretend an order existed before you requested it.

**A split, missing session or provider revision pauses an account** — download the backup and inspect the audit. Do not remove the warning to obtain a performance number. Keep the affected account archived and restart when necessary; automatic unit reconciliation is outside this release.

**Personal data disappeared** — restore a prior full workspace backup. This project does not silently commit private state to GitHub or claim durable cloud storage.
