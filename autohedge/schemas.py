"""
Shared data models for the AutoHedge paper-trading pipeline.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfigError(Exception):
    """Invalid or unsupported runtime configuration."""


class _Model(BaseModel):
    # NaN/inf would silently pass comparisons in the risk gate.
    model_config = ConfigDict(allow_inf_nan=False)


class Bar(_Model):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketSnapshot(_Model):
    ticker: str
    as_of: date
    last_close: float
    sma_20: float
    sma_50: float
    rsi_14: float
    atr_14: float
    vol_20d_annual: float
    return_20d_pct: float
    return_60d_pct: float
    high_52w: float
    low_52w: float
    n_bars: int


class Thesis(_Model):
    ticker: str
    direction: Literal["long", "flat"]
    conviction: float = Field(ge=0, le=1)
    horizon_days: int = Field(ge=1, le=90)
    rationale: str

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


class DirectorOutput(_Model):
    theses: list[Thesis] = Field(min_length=1, max_length=5)


class QuantView(_Model):
    probability_up: float = Field(ge=0, le=1)
    expected_move_pct: float
    summary: str


class OrderProposal(_Model):
    ticker: str
    side: Literal["buy"] = "buy"
    order_type: Literal["limit"] = "limit"
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    notional_usd: float
    expires_after_days: int


class RiskDecision(_Model):
    approved: bool
    reasons: list[str]
    order: OrderProposal | None = None


class Recommendation(_Model):
    id: str
    created_at: datetime
    task: str
    ticker: str | None
    mode: Literal["paper"] = "paper"
    approved: bool
    reasons: list[str]
    thesis: Thesis | None = None
    quant: QuantView | None = None
    snapshot: MarketSnapshot | None = None
    order: OrderProposal | None = None
