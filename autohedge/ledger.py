"""
Append-only JSONL ledger of every recommendation, approved or vetoed.
"""

from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from autohedge.schemas import Recommendation


def append_recommendations(
    path: Path, recs: list[Recommendation]
) -> None:
    """Append one JSON line per recommendation, creating parents."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in recs:
            f.write(rec.model_dump_json() + "\n")


def read_recommendations(path: Path) -> list[Recommendation]:
    """Read the ledger; a missing file is empty, bad lines are skipped."""
    path = Path(path)
    if not path.exists():
        return []
    recs = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                recs.append(Recommendation.model_validate_json(line))
            except ValidationError:
                logger.warning(f"{path}:{n}: skipping corrupt line")
    return recs
