"""
Runtime configuration: trading mode, model name and risk policy.
"""

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
                values[f.name] = float(raw)
            except ValueError:
                raise ConfigError(
                    f"{name} must be a number, got {raw!r}"
                ) from None
        return cls(**values)
