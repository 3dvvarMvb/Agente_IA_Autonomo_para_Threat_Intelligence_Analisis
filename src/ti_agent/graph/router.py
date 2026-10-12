"""Supervisor Router: evaluates state, monitors step & token quotas, and directs execution flow."""

from langgraph.graph import END

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.logging import get_logger
from ti_agent.graph.state import AgentGraphState

logger = get_logger("ti_agent.graph.router")


def supervisor_router(
    state: AgentGraphState,
    settings: Settings | None = None,
) -> str:
    """Evaluate current workflow state and determine the next execution node."""
    cfg = settings or get_settings()
    step = state.get("step", "start")
    iteration = state.get("iteration_count", 0)
    token_count = state.get("token_count", 0)

    logger.debug(
        "Supervisor evaluating state: step='%s', iteration=%d/%d, tokens=%d/%d",
        step,
        iteration,
        cfg.max_iterations,
        token_count,
        cfg.max_tokens_per_execution,
    )

    # 1. Safety limit checks: Iterations and Token limits
    if iteration >= cfg.max_iterations:
        logger.warning(
            "Maximum iteration limit reached (%d >= %d). Halting or finalizing report.",
            iteration,
            cfg.max_iterations,
        )
        if state.get("final_report") is not None:
            return END
        if state.get("extraction_result") is not None and state.get("analysis_result") is not None:
            return "reporter"
        return END

    if token_count >= cfg.max_tokens_per_execution:
        logger.warning(
            "Token budget exhausted (%d >= %d). Forcing termination.",
            token_count,
            cfg.max_tokens_per_execution,
        )
        if state.get("final_report") is not None:
            return END
        if state.get("analysis_result") is not None:
            return "reporter"
        return END

    if state.get("is_finished", False):
        logger.debug("State marked finished. Routing to END.")
        return END

    # 2. Sequential pipeline state transitions
    transitions: dict[str, str] = {
        "start": "extractor",
        "extracted": "analyst",
        "analyzed": "reporter",
        "reported": END,
    }
    if step in transitions:
        return transitions[step]

    # Fallback to end if state unrecognized
    logger.warning("Unrecognized state step '%s'. Terminating graph.", step)
    return END
