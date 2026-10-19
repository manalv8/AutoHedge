"""
Score paper recommendations against what prices actually did, so the
system can be judged on results before any real capital is used.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Literal

from loguru import logger
from pydantic import BaseModel

from autohedge.ledger import read_recommendations
from autohedge.market_data import MarketDataError, fetch_bars
from autohedge.pipeline import BarsFetcher
from autohedge.schemas import Bar, Recommendation

FEE_ROUND_TRIP_PCT = 0.30

Status = Literal["win", "loss", "expired", "unfilled", "pending"]
RESOLVED = ("win", "loss", "expired")


class Outcome(BaseModel):
    rec_id: str
    ticker: str
    status: Status
    return_pct: float | None = None
    benchmark_return_pct: float | None = None


class EvalReport(BaseModel):
    n_total: int
    n_resolved: int
    n_pending: int
    n_unfilled: int
    win_rate: float | None
    avg_return_pct: float | None
    avg_benchmark_return_pct: float | None
    expectancy_pct: float | None


def score_recommendation(
    rec: Recommendation, bars_after: list[Bar], today: date
) -> Outcome:
    """
    Simulate a long limit order over its horizon: calendar days after
    the date of the bar the snapshot was taken from (the recommendation
    date if there is no snapshot).

    The order fills on the first bar whose low reaches the entry. From
    that bar on, a bar touching the stop is a loss (checked first, so a
    bar touching both counts as a loss), exiting at the open if the bar
    gapped through the stop. A bar touching the take-profit is a win;
    on the fill bar this only counts if it opened at or below the entry,
    since otherwise the high may have come before the fill. Without an
    exit, the trade closes at the last close of the horizon.

    The benchmark is buying at the entry and holding to the last close
    of the horizon (or the latest bar while the horizon is open).
    """
    order = rec.order
    start = (
        rec.snapshot.as_of if rec.snapshot else rec.created_at.date()
    )
    end = start + timedelta(days=order.expires_after_days)
    elapsed = today > end
    window = [b for b in bars_after if start < b.date <= end]
    entry = order.entry_price

    def outcome(status: Status, exit_price=None) -> Outcome:
        ret = bench = None
        if exit_price is not None:
            ret = (exit_price / entry - 1) * 100 - FEE_ROUND_TRIP_PCT
            bench = (window[-1].close / entry - 1) * 100
        return Outcome(
            rec_id=rec.id,
            ticker=order.ticker,
            status=status,
            return_pct=ret,
            benchmark_return_pct=bench,
        )

    fill = next(
        (i for i, b in enumerate(window) if b.low <= entry), None
    )
    if fill is None:
        return outcome("unfilled" if elapsed else "pending")

    for i, bar in enumerate(window[fill:], start=fill):
        if bar.low <= order.stop_loss:
            return outcome("loss", min(bar.open, order.stop_loss))
        tp_allowed = i > fill or bar.open <= entry
        if tp_allowed and bar.high >= order.take_profit:
            return outcome("win", max(bar.open, order.take_profit))

    if not elapsed:
        return outcome("pending")
    return outcome("expired", window[-1].close)


def summarize(outcomes: list[Outcome]) -> EvalReport:
    """Aggregate outcomes; pending and unfilled are not scored."""
    resolved = [o for o in outcomes if o.status in RESOLVED]
    returns = [o.return_pct for o in resolved]
    benches = [
        o.benchmark_return_pct
        for o in resolved
        if o.benchmark_return_pct is not None
    ]
    return EvalReport(
        n_total=len(outcomes),
        n_resolved=len(resolved),
        n_pending=sum(o.status == "pending" for o in outcomes),
        n_unfilled=sum(o.status == "unfilled" for o in outcomes),
        win_rate=(
            sum(r > 0 for r in returns) / len(returns)
            if returns
            else None
        ),
        avg_return_pct=mean(returns) if returns else None,
        avg_benchmark_return_pct=mean(benches) if benches else None,
        expectancy_pct=mean(returns) if returns else None,
    )


def evaluate_ledger(
    path: Path,
    fetch: BarsFetcher = fetch_bars,
    today: date | None = None,
) -> tuple[list[Outcome], EvalReport]:
    """Score every approved recommendation in the ledger."""
    today = today or datetime.now(timezone.utc).date()
    cache: dict[str, list[Bar] | None] = {}
    outcomes = []
    for rec in read_recommendations(path):
        if not rec.approved or rec.order is None:
            continue
        ticker = rec.order.ticker
        if ticker not in cache:
            try:
                cache[ticker] = fetch(ticker)
            except MarketDataError as e:
                logger.warning(f"{ticker}: cannot evaluate: {e}")
                cache[ticker] = None
        bars = cache[ticker]
        if bars is None:
            outcomes.append(
                Outcome(rec_id=rec.id, ticker=ticker, status="pending")
            )
            continue
        outcomes.append(score_recommendation(rec, bars, today))
    return outcomes, summarize(outcomes)
