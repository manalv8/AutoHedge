from datetime import date, datetime, timedelta, timezone

import pytest

from autohedge.evaluation import (
    Outcome,
    evaluate_ledger,
    score_recommendation,
    summarize,
)
from autohedge.ledger import append_recommendations
from autohedge.market_data import MarketDataError
from autohedge.schemas import Bar, OrderProposal
from tests.helpers import make_rec

CREATED = date(2026, 10, 19)
AFTER = CREATED + timedelta(days=30)


def order(horizon=5):
    return OrderProposal(
        ticker="NVDA",
        entry_price=100,
        quantity=5,
        stop_loss=95,
        take_profit=110,
        notional_usd=500,
        expires_after_days=horizon,
    )


REC = make_rec(approved=True, reasons=[], order=order())


def snapshot_on(day):
    from autohedge.schemas import MarketSnapshot

    return MarketSnapshot(
        ticker="NVDA",
        as_of=day,
        last_close=100,
        sma_20=100,
        sma_50=100,
        rsi_14=50,
        atr_14=2.5,
        vol_20d_annual=0.3,
        return_20d_pct=0,
        return_60d_pct=0,
        high_52w=120,
        low_52w=80,
        n_bars=250,
    )


def bars(*specs, start=CREATED):
    """specs: (low, high, close[, open]) per day after ``start``."""
    return [
        Bar(
            date=start + timedelta(days=i + 1),
            open=s[3] if len(s) > 3 else s[2],
            high=h,
            low=lo,
            close=c,
            volume=1,
        )
        for i, s in enumerate(specs)
        for lo, h, c in [s[:3]]
    ]


def score(b, today=AFTER):
    return score_recommendation(REC, b, today)


def test_take_profit_hit():
    o = score(bars((99, 101, 100), (100, 111, 110)))
    assert o.status == "win" and o.return_pct == pytest.approx(9.7)
    assert o.benchmark_return_pct == pytest.approx(10)


def test_stop_hit():
    o = score(bars((94, 101, 96)))
    assert o.status == "loss" and o.return_pct == pytest.approx(-5.3)


def test_same_bar_stop_and_tp_counts_as_loss():
    assert score(bars((94, 111, 100))).status == "loss"


def test_never_filled_after_horizon():
    o = score(bars(*[(101, 103, 102)] * 5))
    assert o.status == "unfilled" and o.return_pct is None


def test_horizon_not_elapsed_is_pending():
    o = score(bars((99, 101, 100)), today=CREATED + timedelta(days=2))
    assert o.status == "pending" and o.return_pct is None


def test_unfilled_but_horizon_open_is_pending():
    o = score(bars((101, 103, 102)), today=CREATED + timedelta(days=2))
    assert o.status == "pending"


def test_expired_exits_at_last_close():
    o = score(bars(*[(99, 104, 101)] * 4, (99, 104, 103)))
    assert o.status == "expired"
    assert o.return_pct == pytest.approx(2.7)


def test_bars_beyond_horizon_are_ignored():
    o = score(bars(*[(99, 104, 101)] * 5, (99, 120, 115)))
    assert o.status == "expired"


def _o(status, ret=None, bench=None):
    return Outcome(
        rec_id="x",
        ticker="NVDA",
        status=status,
        return_pct=ret,
        benchmark_return_pct=bench,
    )


def test_summary_excludes_pending_and_unfilled():
    r = summarize(
        [_o("win", 9.7, 10), _o("loss", -5.3, -4), _o("pending"),
         _o("unfilled")]
    )
    assert (r.n_total, r.n_resolved, r.n_pending, r.n_unfilled) == (
        4, 2, 1, 1,
    )
    assert r.win_rate == 0.5
    assert r.expectancy_pct == pytest.approx(2.2)
    assert r.avg_return_pct == pytest.approx(2.2)
    assert r.avg_benchmark_return_pct == pytest.approx(3.0)


def test_summary_empty():
    r = summarize([])
    assert r.win_rate is None and r.expectancy_pct is None
    assert r.n_total == 0


def test_evaluate_ledger_scores_only_approved(tmp_path):
    path = tmp_path / "l.jsonl"
    append_recommendations(
        path, [REC, make_rec(id="v", approved=False, reasons=["no_trade"])]
    )
    outcomes, report = evaluate_ledger(
        path,
        fetch=lambda t: bars((99, 111, 110, 100)),
        today=AFTER,
    )
    assert [o.rec_id for o in outcomes] == ["r1"]
    assert outcomes[0].status == "win" and report.n_resolved == 1


def test_evaluate_ledger_survives_fetch_failure(tmp_path):
    path = tmp_path / "l.jsonl"
    append_recommendations(path, [REC])

    def fetch(t):
        raise MarketDataError("down")

    outcomes, report = evaluate_ledger(path, fetch=fetch, today=AFTER)
    assert outcomes[0].status == "pending" and report.n_pending == 1


def test_gap_below_stop_exits_at_open():
    o = score(bars((99, 101, 100), (78, 82, 80, 80)))
    assert o.status == "loss"
    assert o.return_pct == pytest.approx(-20.3)


def test_fill_bar_tp_ignored_when_opened_above_entry():
    # opens at 112, trades down to fill at 100: high came before fill
    o = score(bars((99, 112, 105, 112)))
    assert o.status == "expired"


def test_fill_bar_tp_counts_when_opened_at_or_below_entry():
    o = score(bars((99, 111, 110, 100)))
    assert o.status == "win"


def test_benchmark_uses_horizon_end_close():
    o = score(
        bars((99, 111, 110, 100), (100, 101, 100), (90, 96, 92), (90, 95, 93),
             (90, 95, 94))
    )
    assert o.status == "win"
    assert o.benchmark_return_pct == pytest.approx(-6)


def test_window_starts_after_snapshot_date():
    # recommendation logged on 10-20 UTC, snapshot bar dated 10-19:
    # the 10-20 session must be evaluated
    rec = make_rec(
        approved=True,
        reasons=[],
        order=order(),
        created_at=datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc),
        snapshot=snapshot_on(CREATED),
    )
    o = score_recommendation(rec, bars((94, 101, 96)), AFTER)
    assert o.status == "loss"
