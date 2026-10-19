"""
Deterministic risk gate: vetoes trades that break the RiskPolicy and
sizes the ones that pass. No LLM is involved in this step.
"""

from autohedge.config import RiskPolicy
from autohedge.schemas import (
    MarketSnapshot,
    OrderProposal,
    QuantView,
    RiskDecision,
    Thesis,
)


def evaluate_risk(
    thesis: Thesis,
    quant: QuantView,
    snapshot: MarketSnapshot,
    policy: RiskPolicy,
) -> RiskDecision:
    """
    Apply every rule, collect all veto reasons, and build a long limit
    order only if none apply.

    Stop sits ``stop_atr_mult`` ATRs below the last close; take-profit
    is ``take_profit_r`` times that distance above it. Notional is the
    smaller of the position cap and the per-trade risk budget divided
    by the stop distance.
    """
    reasons: list[str] = []
    if thesis.direction == "flat":
        reasons.append("no_trade")
    if thesis.conviction < policy.min_conviction:
        reasons.append("low_conviction")
    if quant.probability_up < policy.min_probability_up:
        reasons.append("low_probability")
    if snapshot.vol_20d_annual > policy.max_annual_vol:
        reasons.append("volatility_too_high")

    entry = snapshot.last_close
    stop = entry - policy.stop_atr_mult * snapshot.atr_14
    if snapshot.atr_14 <= 0 or stop <= 0:
        reasons.append("invalid_stop")

    if reasons:
        return RiskDecision(approved=False, reasons=reasons)

    take_profit = entry + policy.take_profit_r * (entry - stop)
    stop_dist = (entry - stop) / entry
    notional = min(
        policy.max_position_pct * policy.equity_usd,
        policy.risk_per_trade_pct * policy.equity_usd / stop_dist,
    )
    order = OrderProposal(
        ticker=snapshot.ticker,
        entry_price=round(entry, 6),
        quantity=round(notional / entry, 8),
        stop_loss=round(stop, 6),
        take_profit=round(take_profit, 6),
        notional_usd=round(notional, 2),
        expires_after_days=thesis.horizon_days,
    )
    return RiskDecision(approved=True, reasons=[], order=order)
