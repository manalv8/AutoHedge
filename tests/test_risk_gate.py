from datetime import date

from autohedge.config import RiskPolicy
from autohedge.risk_gate import evaluate_risk
from autohedge.schemas import MarketSnapshot, QuantView, Thesis


def snap(last_close=100.0, atr_14=2.5, vol=0.4):
    return MarketSnapshot(
        ticker="NVDA",
        as_of=date(2026, 10, 16),
        last_close=last_close,
        sma_20=last_close,
        sma_50=last_close,
        rsi_14=55,
        atr_14=atr_14,
        vol_20d_annual=vol,
        return_20d_pct=1,
        return_60d_pct=2,
        high_52w=last_close * 1.2,
        low_52w=last_close * 0.8,
        n_bars=250,
    )


def thesis(direction="long", conviction=0.8):
    return Thesis(
        ticker="NVDA",
        direction=direction,
        conviction=conviction,
        horizon_days=20,
        rationale="r",
    )


def quant(p=0.6):
    return QuantView(probability_up=p, expected_move_pct=5, summary="s")


def test_approved_order_sizing():
    d = evaluate_risk(thesis(), quant(), snap(), RiskPolicy())
    assert d.approved and d.reasons == []
    o = d.order
    assert (o.entry_price, o.stop_loss, o.take_profit) == (100, 95, 110)
    assert o.notional_usd == 500 and o.quantity == 5
    assert o.expires_after_days == 20 and o.ticker == "NVDA"


def test_position_cap_binds_when_stop_moderate():
    d = evaluate_risk(thesis(), quant(), snap(atr_14=10), RiskPolicy())
    assert d.order.stop_loss == 80 and d.order.notional_usd == 500


def test_risk_budget_caps_position_when_stop_is_wide():
    d = evaluate_risk(thesis(), quant(), snap(atr_14=25), RiskPolicy())
    assert d.order.notional_usd == 200


def test_multiple_vetoes_accumulate():
    d = evaluate_risk(
        thesis(conviction=0.3), quant(0.4), snap(vol=2.0), RiskPolicy()
    )
    assert not d.approved and d.order is None
    assert set(d.reasons) == {
        "low_conviction",
        "low_probability",
        "volatility_too_high",
    }


def test_flat_is_no_trade():
    d = evaluate_risk(thesis("flat"), quant(), snap(), RiskPolicy())
    assert d.reasons == ["no_trade"] and d.order is None


def test_stop_below_zero_is_vetoed():
    d = evaluate_risk(
        thesis(), quant(), snap(last_close=1, atr_14=0.6), RiskPolicy()
    )
    assert "invalid_stop" in d.reasons and not d.approved


def test_zero_atr_is_vetoed():
    d = evaluate_risk(thesis(), quant(), snap(atr_14=0), RiskPolicy())
    assert d.reasons == ["invalid_stop"]
