"""One instrument identity (bare NSE symbol), exact lookup, no guessed tickers."""
from dataclasses import dataclass
from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def canonical_symbol(value: object) -> str:
    text = str(value).strip().upper()
    if text.endswith(".NS"):
        text = text[:-3]
    if text.startswith("NSE:"):
        text = text[4:]
    # No periods, filesystem paths, whitespace or arbitrary provider suffixes.
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9&_-]{0,39}", text):
        raise ValueError("Use a bare NSE symbol, e.g. INFY, or INFY.NS.")
    return text


def provider_symbol(symbol: str) -> str:
    return canonical_symbol(symbol) + ".NS"


def normalize_name(value: object) -> str:
    text = str(value).strip().upper()
    text = re.sub(r"\bLIMITED\b|\bLTD\.?\b", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


@dataclass
class InstrumentRegistry:
    records: dict
    universe: list[str]
    names: dict
    isins: dict

    @classmethod
    def load(cls, root: Path = ROOT):
        frame = pd.read_csv(root / "data/nifty500_tickers.csv", dtype=str).fillna("")
        if "Symbol" not in frame or frame.empty:
            raise ValueError("The bundled universe is empty or invalid.")
        records, universe, names, isins = {}, [], {}, {}
        broader = root / "EQUITY_L.csv"
        if broader.exists():
            for row in pd.read_csv(broader, dtype=str).fillna("").to_dict("records"):
                symbol = canonical_symbol(row["SYMBOL"])
                records[symbol] = {"ticker": symbol, "company": row["NAME OF COMPANY"], "industry": "Outside configured universe", "isin": ""}
        for row in frame.to_dict("records"):
            symbol = canonical_symbol(row["Symbol"])
            if symbol in universe:
                raise ValueError(f"Duplicate universe member: {symbol}")
            universe.append(symbol)
            records[symbol] = {"ticker": symbol, "company": row.get("Company Name", symbol),
                               "industry": row.get("Industry", "Unknown"), "isin": row.get("ISIN Code", "")}
        for symbol, row in records.items():
            key = normalize_name(row["company"])
            names.setdefault(key, []).append(symbol)
            if row["isin"]:
                isins[row["isin"].upper()] = symbol
        return cls(records, universe, names, isins)

    def resolve(self, value: object) -> str | None:
        text = str(value).strip().upper()
        if text in self.isins:
            return self.isins[text]
        try:
            symbol = canonical_symbol(text)
            if symbol in self.records:
                return symbol
        except ValueError:
            pass
        matches = self.names.get(normalize_name(text), [])
        return matches[0] if len(matches) == 1 else None
