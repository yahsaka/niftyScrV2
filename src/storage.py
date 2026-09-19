"""Personal workspace persistence: browser session by default, SQLite opt-in.

Nothing here is used by the public market workflow. Backups are plain JSON and
contain personal information; checksums detect damage, not authenticity.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from src.config import DEFAULT_EXECUTION, DEFAULT_STRATEGY, ExecutionConfig, StrategyConfig
from src.execution import new_ledger, validate_ledger
from src.instruments import canonical_symbol

MAX_BACKUP = 12 * 1024 * 1024


class StorageConflict(ValueError):
    pass


def new_workspace():
    return {"schema_version": 2, "revision": 0, "ledger": new_ledger(), "holdings": [],
            "strategy": asdict(DEFAULT_STRATEGY), "execution": asdict(DEFAULT_EXECUTION),
            "watchlist": [], "saved_filters": {}, "backtests": [], "archived_accounts": [],
            "preferences": {"dark_mode": False, "auto_process": True}}


def validate_workspace(workspace):
    if not isinstance(workspace, dict) or workspace.get("schema_version") != 2:
        raise ValueError("Unsupported personal workspace. The legacy ledger cannot be imported as validated history.")
    validate_ledger(workspace["ledger"])
    StrategyConfig(**workspace["strategy"])
    ExecutionConfig(**workspace["execution"])
    if not isinstance(workspace.get("revision"), int) or workspace["revision"] < 0:
        raise ValueError("Invalid workspace revision.")
    for name in ("holdings", "watchlist", "backtests"):
        if not isinstance(workspace.get(name), list) or len(workspace[name]) > 20_000:
            raise ValueError(f"Invalid {name} collection.")
    seen = set()
    from src.execution import positive
    for holding in workspace["holdings"]:
        symbol = canonical_symbol(holding["ticker"])
        if symbol != holding["ticker"] or symbol in seen:
            raise ValueError("Portfolio symbols must be canonical and unique.")
        seen.add(symbol)
        if not isinstance(holding["quantity"], int) or isinstance(holding["quantity"], bool) or holding["quantity"] < 1:
            raise ValueError("Holdings quantity must be a positive whole number.")
        positive(holding["average_price"], "Average price")
    for symbol in workspace["watchlist"]:
        if canonical_symbol(symbol) != symbol:
            raise ValueError("Invalid watchlist symbol.")
    if not isinstance(workspace.get("saved_filters"), dict) or not isinstance(workspace.get("preferences"), dict):
        raise ValueError("Invalid workspace preferences.")
    for flag in ("dark_mode", "auto_process"):
        if flag in workspace["preferences"] and not isinstance(workspace["preferences"][flag], bool):
            raise ValueError(f"Preference {flag} must be a boolean.")
    if len(workspace["saved_filters"]) > 100:
        raise ValueError("Keep no more than 100 saved filter views.")
    for name, view in workspace["saved_filters"].items():
        if not isinstance(name, str) or not 1 <= len(name) <= 80 or not isinstance(view, dict):
            raise ValueError("Invalid saved filter view.")
        if not isinstance(view.get("query", ""), str) or len(view.get("query", "")) > 200:
            raise ValueError("Invalid saved filter query.")
        score = view.get("score", 3)
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 6:
            raise ValueError("Saved filter condition threshold is invalid.")
        if not isinstance(view.get("industry", "All industries"), str):
            raise ValueError("Invalid saved filter industry.")
        from src.screener import RULES
        if not isinstance(view.get("triggers", []), list) or any(code not in RULES for code in view.get("triggers", [])):
            raise ValueError("Invalid saved filter conditions.")
        if view.get("preset", "All setups") not in {"All setups", "Qualified", "Breakouts", "My watchlist"}:
            raise ValueError("Invalid saved filter preset.")
    archives = workspace.get("archived_accounts", [])
    if not isinstance(archives, list) or len(archives) > 100:
        raise ValueError("Invalid account archive collection.")
    for account in archives:
        if not isinstance(account, dict) or "ledger" not in account:
            raise ValueError("Invalid archived account.")
        validate_ledger(account["ledger"])
    # Reject NaN/Infinity anywhere, including restored analysis reports.
    json.dumps(workspace, allow_nan=False)


def export_backup(workspace: dict) -> bytes:
    validate_workspace(workspace)
    payload = json.dumps(workspace, sort_keys=True, separators=(",", ":"), allow_nan=False)
    envelope = {"kind": "nifty-personal-backup", "schema_version": 2,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(payload.encode()).hexdigest(), "payload": workspace}
    return json.dumps(envelope, indent=2, allow_nan=False).encode()


def import_backup(content: bytes) -> dict:
    if not content or len(content) > MAX_BACKUP:
        raise ValueError("Backup must be a non-empty JSON file smaller than 12 MB.")
    try:
        envelope = json.loads(content)
        if not isinstance(envelope, dict):
            raise ValueError("Backup must contain a JSON object, not an array or scalar.")
        if envelope.get("kind") != "nifty-personal-backup" or envelope.get("schema_version") != 2:
            raise ValueError("Not a version-2 workspace backup. Legacy trades remain unvalidated.")
        payload = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False)
        if hashlib.sha256(payload.encode()).hexdigest() != envelope.get("sha256"):
            raise ValueError("Backup checksum does not match. The current workspace was not changed.")
        validate_workspace(envelope["payload"])
        return deepcopy(envelope["payload"])
    except (KeyError, TypeError, json.JSONDecodeError, OverflowError) as exc:
        raise ValueError("Malformed backup. The current workspace was not changed.") from exc


class SessionStore:
    def __init__(self, session, key="personal_workspace"):
        self.session = session
        self.key = key
        if key not in session:
            session[key] = new_workspace()

    def load(self):
        workspace = deepcopy(self.session[self.key])
        validate_workspace(workspace)
        return workspace

    def save(self, workspace):
        validate_workspace(workspace)
        if workspace["revision"] != self.session[self.key]["revision"]:
            raise StorageConflict("Workspace changed in another action. Reload before retrying.")
        saved = deepcopy(workspace)
        saved["revision"] += 1
        self.session[self.key] = saved
        return deepcopy(saved)


class LocalStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or os.getenv("NIFTY_DB_PATH", ".local/workspace.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, content TEXT NOT NULL)")
                conn.execute("INSERT OR IGNORE INTO workspace VALUES (1, 0, ?)", (json.dumps(new_workspace()),))
        except sqlite3.DatabaseError as exc:
            raise ValueError("Local workspace database is damaged or inaccessible. It was not reset. Restore a verified backup to a new database.") from exc

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def load(self):
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT content FROM workspace WHERE id=1").fetchone()
            workspace = json.loads(row[0])
            validate_workspace(workspace)
            return workspace
        except (sqlite3.DatabaseError, ValueError, TypeError, KeyError) as exc:
            raise ValueError("Cannot read the local workspace; no data was reset.") from exc

    def save(self, workspace):
        validate_workspace(workspace)
        saved = deepcopy(workspace)
        saved["revision"] += 1
        with self.connect() as conn:
            changed = conn.execute("UPDATE workspace SET revision=?, content=? WHERE id=1 AND revision=?",
                                   (saved["revision"], json.dumps(saved, allow_nan=False), workspace["revision"]))
            if changed.rowcount != 1:
                raise StorageConflict("Another session changed this local workspace. Reload before retrying; nothing was overwritten.")
        return saved
