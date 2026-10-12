"""LangGraph state representation for the multi-agent threat intelligence workflow."""

from typing import Annotated, TypedDict

from ti_agent.agents.analyst import AnalysisResult
from ti_agent.models.report import ExtractionResult, ThreatReport


def append_errors(existing: list[str], new_errors: list[str]) -> list[str]:
    """Reducer function for merging error logs in graph state."""
    return existing + new_errors


class AgentGraphState(TypedDict):
    """Shared state dictionary passed across all nodes in the LangGraph workflow."""

    target: str
    extraction_result: ExtractionResult | None
    analysis_result: AnalysisResult | None
    final_report: ThreatReport | None
    errors: Annotated[list[str], append_errors]
    iteration_count: int
    token_count: int
    step: str
    is_finished: bool
