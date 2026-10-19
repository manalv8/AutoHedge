import sys

import pytest

from autohedge import cli
from tests.helpers import (
    QUANT_JSON,
    director_json,
    make_rec,
    rising_bars,
)


def test_run_subcommand_uses_pipeline(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "_run_task",
        lambda task: [make_rec(ticker="NVDA", reasons=["low_conviction"])],
    )
    monkeypatch.setattr(sys, "argv", ["autohedge", "run", "Analyze NVDA"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    out = capsys.readouterr().out
    assert e.value.code == 0
    assert "NVDA" in out and "low_conviction" in out


def test_evaluate_subcommand_on_empty_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["autohedge", "evaluate", "--ledger", str(tmp_path / "none.jsonl")],
    )
    with pytest.raises(SystemExit) as e:
        cli.main()
    out = capsys.readouterr().out
    assert e.value.code == 0 and "Resolved" in out


def test_version_still_works(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["autohedge", "--version"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0


def test_workers_import_has_no_side_effects():
    import autohedge.workers as w

    assert not hasattr(w, "director_agent")
    assert callable(w.make_director) and callable(w.make_quant)


def test_autohedge_run_wires_pipeline(monkeypatch, tmp_path):
    from autohedge import main as main_mod

    monkeypatch.delenv("AUTOHEDGE_MODE", raising=False)
    monkeypatch.setattr(
        main_mod, "make_director", lambda: lambda t: director_json("NVDA")
    )
    monkeypatch.setattr(main_mod, "make_quant", lambda: lambda p: QUANT_JSON)
    monkeypatch.setattr(main_mod, "fetch_bars", lambda t: rising_bars())
    recs = main_mod.AutoHedge(output_dir=str(tmp_path)).run("Analyze NVDA")
    assert recs[0].approved
    assert (tmp_path / "ledger.jsonl").exists()
