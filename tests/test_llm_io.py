import pytest

from autohedge.llm_io import LLMOutputError, parse_llm_json
from autohedge.schemas import QuantView

VALID = '{"probability_up":0.7,"expected_move_pct":3,"summary":"s"}'


def test_plain_json():
    assert parse_llm_json(VALID, QuantView).probability_up == 0.7


def test_fenced_json():
    text = f"Here:\n```json\n{VALID}\n```"
    assert parse_llm_json(text, QuantView).summary == "s"


def test_bare_fence():
    assert parse_llm_json(f"```\n{VALID}\n```", QuantView)


def test_text_around_json():
    text = f"Sure! {VALID} hope it helps"
    assert parse_llm_json(text, QuantView).expected_move_pct == 3


def test_garbage_raises():
    with pytest.raises(LLMOutputError):
        parse_llm_json("I cannot help", QuantView)


def test_schema_violation_raises():
    bad = VALID.replace("0.7", "7")
    with pytest.raises(LLMOutputError):
        parse_llm_json(bad, QuantView)


def test_non_string_raises():
    with pytest.raises(LLMOutputError):
        parse_llm_json(None, QuantView)
