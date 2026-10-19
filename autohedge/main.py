from pathlib import Path

from loguru import logger

from autohedge.market_data import fetch_bars
from autohedge.pipeline import run_pipeline
from autohedge.schemas import Recommendation
from autohedge.workers import make_director, make_quant


class AutoHedge:
    """
    Paper-trading system: runs the fixed Director -> Quant -> risk gate
    pipeline and records every recommendation in a ledger.
    """

    def __init__(
        self,
        name: str = "autohedge",
        description: str = "paper-trading agent hedge fund",
        output_dir: str = "outputs",
    ):
        self.name = name
        self.description = description
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.output_dir / "ledger.jsonl"

    def run(self, task: str) -> list[Recommendation]:
        """Run one paper-trading cycle for ``task``."""
        logger.info("Starting paper-trading cycle")
        return run_pipeline(
            task,
            director=make_director(),
            quant=make_quant(),
            fetch=fetch_bars,
            ledger_path=self.ledger_path,
        )
