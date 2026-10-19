from datetime import date, timedelta

import pandas as pd
import pytest

from autohedge import market_data
from autohedge.market_data import (
    InsufficientHistoryError,
    MarketDataError,
    build_snapshot,
    fetch_bars,
)
from autohedge.schemas import Bar


def _bars(closes, spread=0.0):
    start = date(2026, 1, 1)
    return [
        Bar(
            date=start + timedelta(days=i),
            open=c,
            high=c + spread,
            low=c - spread,
            close=c,
            volume=1000,
        )
        for i, c in enumerate(closes)
    ]


def test_snapshot_linear_series():
    s = build_snapshot("TEST", _bars([float(i) for i in range(1, 101)]))
    assert s.last_close == 100
    assert s.sma_20 == 90.5 and s.sma_50 == 75.5
    assert s.rsi_14 == 100
    assert s.return_20d_pct == pytest.approx((100 / 80 - 1) * 100)
    assert s.return_60d_pct == pytest.approx((100 / 40 - 1) * 100)
    assert (s.high_52w, s.low_52w) == (100, 1)
    assert s.n_bars == 100
    assert s.as_of == date(2026, 1, 1) + timedelta(days=99)


def test_flat_series_rsi_50_and_zero_vol():
    s = build_snapshot("TEST", _bars([10.0] * 60))
    assert s.rsi_14 == 50
    assert s.vol_20d_annual == 0
    assert s.atr_14 == 0


def test_atr_uses_true_range():
    s = build_snapshot("T", _bars([50.0] * 60, spread=1.0))
    assert s.atr_14 == pytest.approx(2.0)


def test_insufficient_history():
    with pytest.raises(InsufficientHistoryError):
        build_snapshot("NEW", _bars([1.0] * 59))


def test_insufficient_history_is_market_data_error():
    assert issubclass(InsufficientHistoryError, MarketDataError)


class _FakeTicker:
    def __init__(self, df):
        self._df = df

    def history(self, period, interval):
        return self._df


def test_fetch_bars_empty_raises(monkeypatch):
    monkeypatch.setattr(
        market_data.yf, "Ticker", lambda t: _FakeTicker(pd.DataFrame())
    )
    with pytest.raises(MarketDataError):
        fetch_bars("ZZZZ")


def test_fetch_bars_drops_nan_rows(monkeypatch):
    idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    df = pd.DataFrame(
        {
            "Open": [1.0, 2.0, 3.0],
            "High": [1.5, 2.5, 3.5],
            "Low": [0.5, 1.5, 2.5],
            "Close": [1.0, float("nan"), 3.0],
            "Volume": [10, 20, 30],
        },
        index=idx,
    )
    monkeypatch.setattr(
        market_data.yf, "Ticker", lambda t: _FakeTicker(df)
    )
    bars = fetch_bars("X")
    assert len(bars) == 2
    assert bars[1].date == date(2026, 1, 3) and bars[1].close == 3.0
