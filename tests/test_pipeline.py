import subprocess
import sys

import pytest

from autohedge.ledger import read_recommendations
from autohedge.market_data import MarketDataError
from autohedge.pipeline import run_pipeline
from autohedge.schemas import ConfigError
from tests.helpers import (
    FIXED_NOW,
    QUANT_JSON,
    director_json,
    make_bars,
    rising_bars,
)


def boom(_):
    raise AssertionError("must not be called")


def _run(tmp_path, director, quant=lambda p: QUANT_JSON, fetch=None):
    return run_pipeline(
        "Analyze",
        director=director,
        quant=quant,
        fetch=fetch or (lambda t: rising_bars()),
        ledger_path=tmp_path / "l.jsonl",
        now=lambda: FIXED_NOW,
    )


@pytest.fixture(autouse=True)
def _paper(monkeypatch):
    monkeypatch.delenv("AUTOHEDGE_MODE", raising=False)
    monkeypatch.delenv("AUTOHEDGE_EQUITY_USD", raising=False)


def test_happy_path_writes_ledger(tmp_path):
    recs = _run(tmp_path, lambda t: director_json("NVDA"))
    assert len(recs) == 1
    r = recs[0]
    assert r.approved and r.order is not None and r.ticker == "NVDA"
    assert r.created_at == FIXED_NOW and r.mode == "paper"
    stored = read_recommendations(tmp_path / "l.jsonl")
    assert [s.id for s in stored] == [r.id]


def test_quant_receives_real_snapshot(tmp_path):
    seen = []
    _run(
        tmp_path,
        lambda t: director_json("NVDA"),
        quant=lambda p: seen.append(p) or QUANT_JSON,
    )
    assert '"last_close"' in seen[0] and '"rsi_14"' in seen[0]
    assert '"conviction"' in seen[0]


def test_unknown_ticker_does_not_stop_batch(tmp_path):
    def fetch(t):
        if t == "ZZZZ":
            raise MarketDataError("no data")
        return rising_bars()

    recs = _run(tmp_path, lambda t: director_json("ZZZZ", "NVDA"), fetch=fetch)
    assert recs[0].reasons == ["no_market_data"] and not recs[0].approved
    assert recs[1].approved
    assert len(read_recommendations(tmp_path / "l.jsonl")) == 2


def test_short_history_is_vetoed(tmp_path):
    recs = _run(
        tmp_path,
        lambda t: director_json("NEW"),
        quant=boom,
        fetch=lambda t: make_bars([1.0] * 59),
    )
    assert recs[0].reasons == ["insufficient_history"]


def test_invalid_director_output_logged(tmp_path):
    recs = _run(tmp_path, lambda t: "sorry", quant=boom)
    assert len(recs) == 1
    assert recs[0].reasons == ["invalid_llm_output"]
    assert recs[0].ticker is None and not recs[0].approved
    assert len(read_recommendations(tmp_path / "l.jsonl")) == 1


def test_invalid_quant_output_is_vetoed(tmp_path):
    recs = _run(
        tmp_path, lambda t: director_json("NVDA"), quant=lambda p: "?"
    )
    assert recs[0].reasons == ["invalid_llm_output"]
    assert recs[0].snapshot is not None and recs[0].order is None


def test_quant_not_called_without_data(tmp_path):
    def fetch(t):
        raise MarketDataError("down")

    recs = _run(
        tmp_path, lambda t: director_json("NVDA"), quant=boom, fetch=fetch
    )
    assert recs[0].reasons == ["no_market_data"]


def test_gate_veto_recorded_with_reasons(tmp_path):
    recs = _run(
        tmp_path, lambda t: director_json("NVDA", conviction=0.2)
    )
    assert recs[0].reasons == ["low_conviction"]
    assert recs[0].quant is not None and recs[0].order is None


def test_live_mode_blocks_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOHEDGE_MODE", "live")
    with pytest.raises(ConfigError):
        _run(tmp_path, boom, quant=boom)
    assert not (tmp_path / "l.jsonl").exists()


def test_pipeline_never_loads_signing_code():
    code = (
        "import sys, autohedge.pipeline; "
        "assert 'autohedge.tools.ultra_tools' not in sys.modules; "
        "assert 'swarms' not in sys.modules"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
