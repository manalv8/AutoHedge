"""
Daily price history (Yahoo Finance) and indicators computed in code,
so the Quant agent reasons over real numbers instead of inventing them.
"""

import math
import statistics
from itertools import pairwise

import yfinance as yf
from loguru import logger

from autohedge.schemas import Bar, MarketSnapshot

MIN_BARS = 60


class MarketDataError(Exception):
    """No usable price data for a ticker."""


class InsufficientHistoryError(MarketDataError):
    """Fewer than MIN_BARS daily bars available."""


def fetch_bars(ticker: str, period: str = "1y") -> list[Bar]:
    """
    Download daily OHLCV bars for a Yahoo symbol (e.g. NVDA, SOL-USD).

    Rows with a missing open/high/low/close are dropped.

    Raises
    ------
    MarketDataError
        If Yahoo returns no usable rows.
    """
    symbol = ticker.strip().upper()
    try:
        df = yf.Ticker(symbol).history(period=period, interval="1d")
    except Exception as e:
        raise MarketDataError(f"{symbol}: download failed: {e}") from e
    if df is None or df.empty:
        raise MarketDataError(f"{symbol}: no price data")
    ohlc = df[["Open", "High", "Low", "Close"]]
    usable = ohlc.apply(lambda col: col.map(math.isfinite)).all(axis=1)
    df = df[usable & (ohlc > 0).all(axis=1)]
    if df.empty:
        raise MarketDataError(f"{symbol}: no price data")
    bars = [
        Bar(
            date=ts.date(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=_volume(row.get("Volume")),
        )
        for ts, row in df.iterrows()
    ]
    logger.debug(f"{symbol}: {len(bars)} daily bars")
    return bars


def _volume(raw) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _sma(values: list[float], n: int) -> float:
    return sum(values[-n:]) / n


def _rsi(closes: list[float], n: int = 14) -> float:
    changes = [b - a for a, b in pairwise(closes)]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        avg_gain = (avg_gain * (n - 1) + g) / n
        avg_loss = (avg_loss * (n - 1) + l) / n
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _atr(bars: list[Bar], n: int = 14) -> float:
    window = bars[-(n + 1) :]
    trs = [
        max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        for prev, cur in pairwise(window)
    ]
    return sum(trs) / n


def _annual_vol(closes: list[float], n: int = 20) -> float:
    window = closes[-(n + 1) :]
    rets = [math.log(b / a) for a, b in pairwise(window)]
    return statistics.stdev(rets) * math.sqrt(252)


def _return_pct(closes: list[float], n: int) -> float:
    return (closes[-1] / closes[-1 - n] - 1) * 100


def build_snapshot(ticker: str, bars: list[Bar]) -> MarketSnapshot:
    """
    Compute the indicator snapshot from daily bars (oldest first).

    Raises
    ------
    InsufficientHistoryError
        If fewer than MIN_BARS bars are given.
    """
    if len(bars) < MIN_BARS:
        raise InsufficientHistoryError(
            f"{ticker}: {len(bars)} bars, need {MIN_BARS}"
        )
    if any(
        not math.isfinite(v) or v <= 0
        for b in bars
        for v in (b.open, b.high, b.low, b.close)
    ):
        raise InsufficientHistoryError(
            f"{ticker}: non-positive or non-finite prices"
        )
    closes = [b.close for b in bars]
    year = bars[-252:]
    return MarketSnapshot(
        ticker=ticker,
        as_of=bars[-1].date,
        last_close=closes[-1],
        sma_20=_sma(closes, 20),
        sma_50=_sma(closes, 50),
        rsi_14=_rsi(closes),
        atr_14=_atr(bars),
        vol_20d_annual=_annual_vol(closes),
        return_20d_pct=_return_pct(closes, 20),
        return_60d_pct=_return_pct(closes, min(60, len(closes) - 1)),
        high_52w=max(b.high for b in year),
        low_52w=min(b.low for b in year),
        n_bars=len(bars),
    )
