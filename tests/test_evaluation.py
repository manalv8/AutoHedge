from datetime import date, timedelta

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


def bars(*specs):
    """specs: (low, high, close) per day starting the day after CREATED."""
    return [
        Bar(
            date=CREATED + timedelta(days=i + 1),
            open=c,
            high=h,
            low=lo,
            close=c,
            volume=1,
        )
        for i, (lo, h, c) in enumerate(specs)
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
        fetch=lambda t: bars((99, 111, 110)),
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
