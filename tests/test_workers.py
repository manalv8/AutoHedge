from autohedge.llm_io import parse_llm_json
from autohedge.schemas import QuantView


def test_make_quant_returns_only_latest_reply(monkeypatch):
    from swarms import Agent

    from autohedge.workers import make_quant

    replies = iter(
        [
            '{"probability_up":0.9,"expected_move_pct":1,"summary":"A"}',
            '{"probability_up":0.1,"expected_move_pct":1,"summary":"B"}',
        ]
    )
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setattr(
        Agent, "call_llm", lambda self, *a, **k: next(replies)
    )
    quant = make_quant()
    first = parse_llm_json(quant("thesis 1"), QuantView)
    second = parse_llm_json(quant("thesis 2"), QuantView)
    assert first.probability_up == 0.9
    assert second.probability_up == 0.1
