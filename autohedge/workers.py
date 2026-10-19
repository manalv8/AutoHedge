"""
AutoHedge workers: factories for the two LLM roles in the pipeline
(Director and Quant). Agents are created on demand, not at import.
"""

from datetime import datetime

from autohedge.config import get_model_name
from autohedge.pipeline import LLM
from autohedge.prompts import DIRECTOR_JSON_PROMPT, QUANT_JSON_PROMPT


def _system_suffix() -> str:
    now = datetime.now().astimezone().strftime("%A, %B %d, %Y at %H:%M %Z")
    return f"\n\nCurrent date and time (use this as now): {now}"


def _make_agent(name: str, system_prompt: str) -> LLM:
    from swarms import Agent

    agent = Agent(
        agent_name=name,
        system_prompt=system_prompt + _system_suffix(),
        model_name=get_model_name(),
        max_loops=1,
        output_type="str",
    )
    return lambda text: str(agent.run(text))


def make_director() -> LLM:
    """LLM that turns a task into a JSON list of theses."""
    return _make_agent("Trading-Director", DIRECTOR_JSON_PROMPT)


def make_quant() -> LLM:
    """LLM that reads a thesis + real market snapshot, returns JSON."""
    return _make_agent("Quant-Analyst", QUANT_JSON_PROMPT)
