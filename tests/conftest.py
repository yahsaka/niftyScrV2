from datetime import datetime
import pandas as pd
import pytest
from src.config import ExecutionConfig
from src.execution import create_order, new_ledger
from src.freshness import IST
from src.instruments import InstrumentRegistry


@pytest.fixture
def registry():
    return InstrumentRegistry.load()


@pytest.fixture
def bars():
    dates = pd.bdate_range("2025-01-01", periods=30)
    return pd.DataFrame({"Open": 100.0, "High": 105.0, "Low": 98.0, "Close": 102.0,
                         "Adj Close": 102.0, "Volume": 10000.0, "Dividends": 0.0, "Stock Splits": 0.0}, index=dates)


@pytest.fixture
def setup():
    return {"ticker": "INFY", "last_date": "2025-01-01", "close": 102.0, "atr_at_signal": 5.0, "score": 6}


@pytest.fixture
def ledger(setup):
    return create_order(new_ledger(), setup, 10000.0, 2.0, ExecutionConfig(hold_sessions=5),
                        requested_at=datetime(2025, 1, 1, 16, 30, tzinfo=IST))
