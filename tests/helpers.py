import json
from datetime import date, datetime, timedelta, timezone

from autohedge.schemas import Bar, Recommendation


def make_bars(closes, start=date(2026, 1, 1), spread=1.0):
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


def rising_bars(n=100):
    return make_bars([100.0 + i * 0.5 for i in range(n)])


def director_json(*tickers, direction="long", conviction=0.8):
    return json.dumps(
        {
            "theses": [
                {
                    "ticker": t,
                    "direction": direction,
                    "conviction": conviction,
                    "horizon_days": 20,
                    "rationale": "trend",
                }
                for t in tickers
            ]
        }
    )


QUANT_JSON = json.dumps(
    {"probability_up": 0.6, "expected_move_pct": 4, "summary": "ok"}
)

FIXED_NOW = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)


def make_rec(**kw):
    base = {
        "id": "r1",
        "created_at": FIXED_NOW,
        "task": "t",
        "ticker": "NVDA",
        "approved": False,
        "reasons": ["no_trade"],
    }
    base.update(kw)
    return Recommendation(**base)
