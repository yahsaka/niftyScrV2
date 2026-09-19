"""Versioned, validated strategy and execution assumptions."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math


@dataclass(frozen=True)
class StrategyConfig:
    watchlist_min_score: int = 3
    qualified_min_score: int = 5
    max_pct_above_50ema: float = 0.15

    def __post_init__(self):
        if not (type(self.watchlist_min_score) is int and type(self.qualified_min_score) is int
                and 0 <= self.watchlist_min_score <= self.qualified_min_score <= 6):
            raise ValueError("Scores must be integers with 0 ≤ watchlist ≤ qualified ≤ 6.")
        if not math.isfinite(self.max_pct_above_50ema) or not 0 <= self.max_pct_above_50ema <= 1:
            raise ValueError("Maximum extension must be between 0 and 100%.")

    @property
    def version(self) -> str:
        digest = hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:10]
        return f"six-rule-v2-{digest}"


@dataclass(frozen=True)
class ExecutionConfig:
    hold_sessions: int = 20
    atr_multiplier: float = 2.0
    entry_slippage_bps: float = 5.0
    exit_slippage_bps: float = 5.0
    round_trip_cost_bps: float = 20.0

    def __post_init__(self):
        if type(self.hold_sessions) is not int or not 1 <= self.hold_sessions <= 252:
            raise ValueError("Holding period must be an integer between 1 and 252 sessions.")
        if not math.isfinite(self.atr_multiplier) or not 0 < self.atr_multiplier <= 20:
            raise ValueError("ATR multiplier must be finite, positive and no larger than 20.")
        for name in ("entry_slippage_bps", "exit_slippage_bps", "round_trip_cost_bps"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value <= 1000:
                raise ValueError(f"{name} must be between 0 and 1,000 basis points.")

    @property
    def fee_rate(self) -> float:
        # Half the configurable round-trip rate on each side's actual notional.
        return self.round_trip_cost_bps / 20_000


DEFAULT_STRATEGY = StrategyConfig()
DEFAULT_EXECUTION = ExecutionConfig()
