"""
Runtime configuration: trading mode, model name and risk policy.
"""

import math
import os
from dataclasses import dataclass, fields
from typing import Literal

from autohedge.schemas import ConfigError


def get_mode() -> Literal["paper"]:
    """Return the trading mode; only paper trading is supported."""
    mode = os.getenv("AUTOHEDGE_MODE", "paper").strip().lower()
    if mode != "paper":
        raise ConfigError(
            "live trading is not implemented; only "
            "AUTOHEDGE_MODE=paper is supported"
        )
    return "paper"


def get_model_name() -> str:
    """Return the LLM model name used by the agents."""
    return os.getenv("AUTOHEDGE_MODEL", "gpt-4.1")


# (low, high, low_inclusive); every value must also be finite.
_BOUNDS = {
    "equity_usd": (0, math.inf, False),
    "min_conviction": (0, 1, True),
    "min_probability_up": (0, 1, True),
    "max_position_pct": (0, 1, False),
    "risk_per_trade_pct": (0, 1, False),
    "stop_atr_mult": (0, math.inf, False),
    "take_profit_r": (0, math.inf, False),
    "max_annual_vol": (0, math.inf, False),
}


def _check(name: str, field: str, value: float) -> float:
    low, high, low_inclusive = _BOUNDS[field]
    above = value >= low if low_inclusive else value > low
    if not (math.isfinite(value) and above and value <= high):
        raise ConfigError(f"{name}={value!r} is out of range")
    return value


@dataclass(frozen=True)
class RiskPolicy:
    """Hard limits applied by the deterministic risk gate."""

    equity_usd: float = 10_000
    min_conviction: float = 0.6
    min_probability_up: float = 0.55
    max_position_pct: float = 0.05
    risk_per_trade_pct: float = 0.01
    stop_atr_mult: float = 2.0
    take_profit_r: float = 2.0
    max_annual_vol: float = 1.20

    @classmethod
    def from_env(cls) -> "RiskPolicy":
        """Build a policy, overriding defaults with AUTOHEDGE_<FIELD>."""
        values = {}
        for f in fields(cls):
            name = f"AUTOHEDGE_{f.name.upper()}"
            raw = os.getenv(name)
            if raw is None:
                continue
            try:
                value = float(raw)
            except ValueError:
                raise ConfigError(
                    f"{name} must be a number, got {raw!r}"
                ) from None
            values[f.name] = _check(name, f.name, value)
        return cls(**values)
