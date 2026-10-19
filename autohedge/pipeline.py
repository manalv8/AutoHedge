"""
Fixed-order paper-trading pipeline:
Director (LLM) -> market data (code) -> Quant (LLM) -> risk gate (code)
-> ledger. LLMs and the price fetcher are injected so the flow can be
tested without network access.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from autohedge.config import RiskPolicy, get_mode
from autohedge.ledger import append_recommendations
from autohedge.llm_io import LLMOutputError, parse_llm_json
from autohedge.market_data import (
    InsufficientHistoryError,
    MarketDataError,
    build_snapshot,
    fetch_bars,
)
from autohedge.risk_gate import evaluate_risk
from autohedge.schemas import (
    Bar,
    DirectorOutput,
    MarketSnapshot,
    QuantView,
    Recommendation,
    Thesis,
)

LLM = Callable[[str], str]
BarsFetcher = Callable[[str], list[Bar]]

DEFAULT_LEDGER = Path("outputs/ledger.jsonl")


def _quant_input(thesis: Thesis, snapshot: MarketSnapshot) -> str:
    return (
        f"Thesis:\n{thesis.model_dump_json()}\n\n"
        f"Market snapshot (computed from real prices):\n"
        f"{snapshot.model_dump_json()}"
    )


def _evaluate_thesis(
    thesis: Thesis,
    *,
    quant: LLM,
    fetch: BarsFetcher,
    policy: RiskPolicy,
    base: dict,
) -> Recommendation:
    rec = dict(base, ticker=thesis.ticker, thesis=thesis)
    try:
        snapshot = build_snapshot(thesis.ticker, fetch(thesis.ticker))
    except InsufficientHistoryError as e:
        logger.warning(str(e))
        return Recommendation(
            **rec, approved=False, reasons=["insufficient_history"]
        )
    except MarketDataError as e:
        logger.warning(str(e))
        return Recommendation(
            **rec, approved=False, reasons=["no_market_data"]
        )
    rec["snapshot"] = snapshot

    try:
        view = parse_llm_json(
            quant(_quant_input(thesis, snapshot)), QuantView
        )
    except LLMOutputError as e:
        logger.warning(f"{thesis.ticker}: quant output: {e}")
        return Recommendation(
            **rec, approved=False, reasons=["invalid_llm_output"]
        )
    rec["quant"] = view

    decision = evaluate_risk(thesis, view, snapshot, policy)
    return Recommendation(
        **rec,
        approved=decision.approved,
        reasons=decision.reasons,
        order=decision.order,
    )


def run_pipeline(
    task: str,
    *,
    director: LLM,
    quant: LLM,
    fetch: BarsFetcher = fetch_bars,
    policy: RiskPolicy | None = None,
    ledger_path: Path = DEFAULT_LEDGER,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> list[Recommendation]:
    """
    Run one paper-trading cycle for ``task`` and append every resulting
    recommendation to ``ledger_path``.

    Raises
    ------
    ConfigError
        If AUTOHEDGE_MODE is anything other than "paper".
    """
    mode = get_mode()
    policy = policy or RiskPolicy.from_env()
    created_at = now()

    def base() -> dict:
        return {
            "id": uuid.uuid4().hex,
            "created_at": created_at,
            "task": task,
            "mode": mode,
        }

    try:
        plan = parse_llm_json(director(task), DirectorOutput)
    except LLMOutputError as e:
        logger.warning(f"director output: {e}")
        recs = [
            Recommendation(
                **base(),
                ticker=None,
                approved=False,
                reasons=["invalid_llm_output"],
            )
        ]
    else:
        recs = [
            _evaluate_thesis(
                thesis,
                quant=quant,
                fetch=fetch,
                policy=policy,
                base=base(),
            )
            for thesis in plan.theses
        ]

    append_recommendations(ledger_path, recs)
    return recs
