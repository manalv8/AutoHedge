import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from autohedge.config import RiskPolicy, get_mode
from autohedge.schemas import ConfigError, QuantView, Thesis


def test_mode_defaults_to_paper(monkeypatch):
    monkeypatch.delenv("AUTOHEDGE_MODE", raising=False)
    assert get_mode() == "paper"


def test_live_mode_is_blocked(monkeypatch):
    monkeypatch.setenv("AUTOHEDGE_MODE", "live")
    with pytest.raises(
        ConfigError, match="live trading is not implemented"
    ):
        get_mode()


def test_policy_defaults(monkeypatch):
    for k in list(os.environ):
        if k.startswith("AUTOHEDGE_"):
            monkeypatch.delenv(k)
    p = RiskPolicy.from_env()
    assert (
        p.equity_usd,
        p.max_position_pct,
        p.risk_per_trade_pct,
    ) == (10_000, 0.05, 0.01)


def test_policy_env_override(monkeypatch):
    monkeypatch.setenv("AUTOHEDGE_EQUITY_USD", "2500")
    assert RiskPolicy.from_env().equity_usd == 2500.0


def test_policy_rejects_non_numeric_env(monkeypatch):
    monkeypatch.setenv("AUTOHEDGE_MIN_CONVICTION", "high")
    with pytest.raises(ConfigError, match="AUTOHEDGE_MIN_CONVICTION"):
        RiskPolicy.from_env()


def test_thesis_rejects_out_of_range_conviction():
    with pytest.raises(ValidationError):
        Thesis(
            ticker="NVDA",
            direction="long",
            conviction=1.5,
            horizon_days=10,
            rationale="x",
        )


def test_config_import_does_not_load_swarms():
    code = (
        "import sys, autohedge.config; "
        "assert 'swarms' not in sys.modules"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AUTOHEDGE_MIN_CONVICTION", "nan"),
        ("AUTOHEDGE_MAX_ANNUAL_VOL", "inf"),
        ("AUTOHEDGE_STOP_ATR_MULT", "0"),
        ("AUTOHEDGE_EQUITY_USD", "-5"),
        ("AUTOHEDGE_RISK_PER_TRADE_PCT", "1.5"),
    ],
)
def test_policy_rejects_unsafe_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match=name):
        RiskPolicy.from_env()


def test_quant_view_rejects_nan():
    with pytest.raises(ValidationError):
        QuantView(
            probability_up=0.6,
            expected_move_pct=float("nan"),
            summary="s",
        )


def test_thesis_ticker_is_normalized():
    t = Thesis(
        ticker=" nvda ",
        direction="long",
        conviction=0.7,
        horizon_days=5,
        rationale="x",
    )
    assert t.ticker == "NVDA"
