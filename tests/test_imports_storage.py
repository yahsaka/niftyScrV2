from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
import json
import sqlite3
import pandas as pd
import pytest
from src.imports import infer_mapping, merge_holdings, normalize_rows, read_upload
from src.instruments import canonical_symbol, provider_symbol
from src.storage import LocalStore, SessionStore, StorageConflict, export_backup, import_backup, new_workspace


@pytest.mark.parametrize("column", ["Symbol", "Ticker", "tradingsymbol", "ISIN"])
def test_csv_column_aliases(column, registry):
    instrument = "INE009A01021" if column == "ISIN" else "INFY.NS"
    frame = read_upload(f"{column},Quantity,Average Price\n{instrument},10,1500\n".encode(), "holdings.csv")
    result = normalize_rows(frame, infer_mapping(frame.columns), registry)
    assert result.accepted[0]["ticker"] == "INFY" and not result.rejected


def test_consumed_stream_can_be_parsed_repeatedly(registry):
    uploaded = BytesIO(b"Symbol,Quantity,Average Price\nINFY,10,1500\n")
    uploaded.read()
    for _ in range(2):
        frame = read_upload(uploaded, "holdings.csv")
        assert normalize_rows(frame, infer_mapping(frame.columns), registry).accepted[0]["quantity"] == 10


def test_csv_preamble_and_semicolon_separator(registry):
    content = b"Broker export\nAccount summary\nSymbol;Qty;Avg. price\nTCS;5;3500\n"
    frame = read_upload(content, "test.csv")
    assert normalize_rows(frame, infer_mapping(frame.columns), registry).accepted[0]["ticker"] == "TCS"


def test_xlsx_with_preamble(registry):
    content = BytesIO()
    pd.DataFrame([["Holdings export", None, None], ["Ticker", "Quantity", "Average Price"], ["INFY", 10, 1500]]).to_excel(content, header=False, index=False)
    frame = read_upload(content, "holdings.xlsx")
    assert normalize_rows(frame, infer_mapping(frame.columns), registry).accepted[0]["average_price"] == 1500


def test_exact_company_matching_no_guessing(registry):
    assert registry.resolve("Infosys Limited") == "INFY"
    assert registry.resolve("Definitely Not A Listed Company Ltd") is None
    assert registry.resolve("INFY.NS") == "INFY"
    assert registry.resolve("NSE:INFY") == "INFY"


@pytest.mark.parametrize("bad", ["../../secret", "INFY.BO", "^NSEI", "", "INFY;rm", "=FORMULA"])
def test_canonical_symbol_is_path_safe(bad):
    with pytest.raises(ValueError):
        canonical_symbol(bad)


def test_unmatched_invalid_rows_are_explicit(registry):
    frame = pd.DataFrame({"Symbol": ["INFY", "Unknown Co", "TCS", "ITC"], "Quantity": [10, 5, -2, 3], "Average Price": [1500, 100, 3000, "not a number"]})
    result = normalize_rows(frame, infer_mapping(frame.columns), registry)
    assert len(result.accepted) == 1 and len(result.rejected) == 3
    assert [row["row"] for row in result.rejected] == [2, 3, 4]


def test_rejected_row_can_be_corrected(registry):
    frame = pd.DataFrame({"Symbol": ["Unknown"], "Qty": ["bad"], "Avg Price": [-2]})
    overrides = {"0": {"instrument": "INFY", "quantity": 5, "average_price": 1400}}
    result = normalize_rows(frame, infer_mapping(frame.columns), registry, overrides)
    assert len(result.accepted) == 1 and not result.rejected


def test_weighted_duplicate_holdings(registry):
    rows = [{"ticker": "INFY", "quantity": 10, "average_price": 100}, {"ticker": "INFY", "quantity": 20, "average_price": 130}]
    merged = merge_holdings([], rows)
    assert merged[0]["quantity"] == 30 and merged[0]["average_price"] == 120


def test_currency_and_comma_numbers(registry):
    frame = pd.DataFrame({"Symbol": ["INFY"], "Quantity": ["1,000"], "Average Price": ["₹1,500.50"]})
    result = normalize_rows(frame, infer_mapping(frame.columns), registry)
    assert result.accepted[0]["average_price"] == 1500.5


def test_invalid_mapping_rejected(registry):
    with pytest.raises(ValueError, match="different"):
        normalize_rows(pd.DataFrame({"A": [1]}), {"instrument": "A", "quantity": "A", "average_price": "A"}, registry)


def test_backup_roundtrip_preserves_everything(ledger):
    workspace = new_workspace()
    workspace["ledger"] = ledger
    assert import_backup(export_backup(workspace)) == workspace


def test_modified_backup_checksum_fails():
    backup = json.loads(export_backup(new_workspace()))
    backup["payload"]["ledger"]["initial_cash"] = 999
    with pytest.raises(ValueError, match="checksum"):
        import_backup(json.dumps(backup).encode())


@pytest.mark.parametrize("payload", [b"broken", b"[]", b"{}", b'{"schema_version":1}'])
def test_corrupt_or_legacy_backups_are_not_silently_reset(payload):
    with pytest.raises((ValueError, AttributeError)):
        import_backup(payload)


def test_session_isolation():
    a, b = SessionStore({}), SessionStore({})
    value = a.load()
    value["watchlist"] = ["INFY"]
    a.save(value)
    assert b.load()["watchlist"] == []


def test_demo_session_is_separate_from_personal():
    state = {}
    real, demo = SessionStore(state), SessionStore(state, key="demo_workspace")
    value = demo.load()
    value["watchlist"] = ["TCS"]
    demo.save(value)
    assert real.load()["watchlist"] == []


def test_local_store_survives_reopen(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = LocalStore(path)
    data = store.load()
    data["watchlist"] = ["INFY"]
    store.save(data)
    assert LocalStore(path).load()["watchlist"] == ["INFY"]


def test_concurrent_writes_do_not_lose_updates(tmp_path):
    store = LocalStore(tmp_path / "state.sqlite3")
    a, b = store.load(), store.load()
    a["watchlist"], b["watchlist"] = ["INFY"], ["TCS"]
    def save(value):
        try:
            store.save(value)
            return "saved"
        except StorageConflict:
            return "conflict"
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, [a, b]))
    assert sorted(results) == ["conflict", "saved"]


def test_corrupt_sqlite_is_not_overwritten(tmp_path):
    path = tmp_path / "bad.sqlite3"
    path.write_bytes(b"not sqlite")
    with pytest.raises(ValueError, match="not reset"):
        LocalStore(path)
    assert path.read_bytes() == b"not sqlite"
