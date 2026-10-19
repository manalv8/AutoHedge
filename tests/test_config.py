import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from autohedge.config import RiskPolicy, get_mode
from autohedge.schemas import ConfigError, Thesis


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
