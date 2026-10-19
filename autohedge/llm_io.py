"""
Extract and validate JSON from free-form LLM replies.
"""

import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LLMOutputError(Exception):
    """The LLM reply did not contain JSON matching the schema."""


def parse_llm_json(text: str, model: type[T]) -> T:
    """
    Parse ``text`` into ``model``.

    Uses the first fenced code block if present, otherwise the span
    from the first ``{`` to the last ``}``.

    Raises
    ------
    LLMOutputError
        If no JSON object is found or it fails validation.
    """
    if not isinstance(text, str):
        raise LLMOutputError(f"expected str, got {type(text).__name__}")
    fence = _FENCE.search(text)
    if fence:
        candidate = fence.group(1).strip()
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end < start:
            raise LLMOutputError(f"no JSON object in: {text[:200]!r}")
        candidate = text[start : end + 1]
    try:
        return model.model_validate_json(candidate)
    except ValidationError as e:
        raise LLMOutputError(
            f"invalid {model.__name__}: {e.errors()[:3]} "
            f"in: {text[:200]!r}"
        ) from e
