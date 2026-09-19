"""Byte-safe CSV/XLSX ingestion, explicit columns and row-level correction."""
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
import csv
import math
import re
import zipfile
import pandas as pd
from src.instruments import InstrumentRegistry

MAX_UPLOAD = 5 * 1024 * 1024
ALIASES = {
    "instrument": {"symbol", "ticker", "tradingsymbol", "trading symbol", "stock", "stock name", "company", "company name", "security", "scrip", "isin"},
    "quantity": {"quantity", "qty", "balance", "holding quantity", "shares", "net qty", "available quantity"},
    "average_price": {"average price", "avg price", "avg. price", "avg cost", "average cost", "avg. cost", "buy price", "purchase price", "cost price", "average buy price"},
}


def key(value) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("_", " "))


def upload_bytes(file) -> bytes:
    if isinstance(file, bytes):
        content = file
    elif hasattr(file, "getvalue"):
        content = file.getvalue()
    else:
        position = file.tell() if hasattr(file, "tell") else None
        if hasattr(file, "seek"):
            file.seek(0)
        content = file.read()
        if position is not None:
            file.seek(position)
    if not isinstance(content, bytes):
        content = content.encode("utf-8")
    if not content or len(content) > MAX_UPLOAD:
        raise ValueError("Upload a non-empty CSV or XLSX smaller than 5 MB.")
    return content


def infer_mapping(columns) -> dict:
    mapping = {}
    for field, aliases in ALIASES.items():
        matches = [str(column) for column in columns if key(column) in aliases]
        if len(matches) == 1:
            mapping[field] = matches[0]
    return mapping


def _header_score(values) -> int:
    normalized = {key(value) for value in values}
    return sum(bool(normalized & aliases) for aliases in ALIASES.values())


def read_upload(file, filename: str) -> pd.DataFrame:
    content = upload_bytes(file)
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("cp1252")
        # Detect the most plausible header among the first 30 lines and three
        # common delimiters, using separate buffers rather than consumed streams.
        lines = text.splitlines()
        candidates = []
        for delimiter in (",", ";", "\t"):
            for idx, line in enumerate(lines[:30]):
                fields = next(csv.reader([line], delimiter=delimiter))
                candidates.append((_header_score(fields), len(fields), -idx, delimiter))
        score, width, negative_header, delimiter = max(candidates)
        header = -negative_header if score >= 2 else 0
        try:
            frame = pd.read_csv(StringIO(text), sep=delimiter if score >= 2 else ",", skiprows=header, dtype=str)
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            raise ValueError("Cannot parse this CSV. Use the supplied three-column template or select a standard broker export.") from exc
    elif suffix == ".xlsx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if sum(entry.file_size for entry in archive.infolist()) > 30 * 1024 * 1024:
                    raise ValueError("Expanded workbook is too large (30 MB limit).")
            raw = pd.read_excel(BytesIO(content), header=None, dtype=str, engine="openpyxl")
            scores = [(_header_score(row), -idx) for idx, row in enumerate(raw.head(30).values)]
            score, negative_header = max(scores, default=(0, 0))
            header = -negative_header if score >= 2 else 0
            frame = pd.read_excel(BytesIO(content), header=header, dtype=str, engine="openpyxl")
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValueError("This is not a valid XLSX workbook.") from exc
    else:
        raise ValueError("Supported formats: CSV and XLSX. PDF/CAS and broker login integrations are not implemented.")
    frame = frame.dropna(how="all").fillna("")
    frame.columns = [str(column).strip() for column in frame.columns]
    if frame.empty or len(frame) > 10_000 or len(frame.columns) > 100:
        raise ValueError("Upload must contain 1–10,000 rows and no more than 100 columns.")
    return frame.reset_index(drop=True)


def number(value, label: str) -> float:
    text = str(value).strip().replace(",", "").replace("₹", "").replace("\u00a0", "")
    try:
        value = float(text)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label} is not a valid number.") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return value


@dataclass
class ImportResult:
    accepted: list[dict]
    rejected: list[dict]


def normalize_rows(frame: pd.DataFrame, mapping: dict, registry: InstrumentRegistry,
                   overrides: dict | None = None) -> ImportResult:
    if set(mapping) != set(ALIASES) or any(mapping[field] not in frame for field in ALIASES):
        raise ValueError("Map an instrument, quantity and average-price column before importing.")
    if len(set(mapping.values())) != 3:
        raise ValueError("Each field must map to a different source column.")
    accepted, rejected = [], []
    for idx, row in frame.iterrows():
        raw = {field: row[column] for field, column in mapping.items()}
        raw.update((overrides or {}).get(str(idx), {}))
        try:
            ticker = registry.resolve(raw["instrument"])
            if ticker is None:
                raise ValueError("Instrument is unmatched. Choose an exact symbol; no ticker was guessed.")
            quantity = number(raw["quantity"], "Quantity")
            if quantity != int(quantity):
                raise ValueError("NSE equity quantity must be a whole number.")
            average = number(raw["average_price"], "Average price")
            accepted.append({"ticker": ticker, "quantity": int(quantity), "average_price": average,
                             "company": registry.records[ticker]["company"], "industry": registry.records[ticker]["industry"]})
        except ValueError as exc:
            rejected.append({"row": int(idx) + 1, **raw, "reason": str(exc)})
    return ImportResult(merge_holdings([], accepted), rejected)


def merge_holdings(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = {}
    for row in [*existing, *incoming]:
        ticker = row["ticker"]
        if ticker not in merged:
            merged[ticker] = dict(row)
        else:
            previous = merged[ticker]
            total_quantity = previous["quantity"] + row["quantity"]
            previous["average_price"] = (previous["quantity"] * previous["average_price"] + row["quantity"] * row["average_price"]) / total_quantity
            previous["quantity"] = total_quantity
    return [merged[ticker] for ticker in sorted(merged)]
