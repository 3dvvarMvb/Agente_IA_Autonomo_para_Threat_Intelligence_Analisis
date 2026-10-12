"""LangGraph multi-agent workflow compilation and threat intelligence execution engine."""

import asyncio
import time
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ti_agent.agents.analyst import ContextAnalystAgent
from ti_agent.agents.base import estimate_token_count
from ti_agent.agents.extractor import ExtractorAgent
from ti_agent.agents.reporter import ReporterAgent
from ti_agent.core.config import Settings, get_settings
from ti_agent.core.logging import get_logger
from ti_agent.graph.router import supervisor_router
from ti_agent.graph.state import AgentGraphState
from ti_agent.models.report import ThreatReport

logger = get_logger("ti_agent.graph.workflow")


def create_nodes(
    settings: Settings,
    extractor: ExtractorAgent | None = None,
    analyst: ContextAnalystAgent | None = None,
    reporter: ReporterAgent | None = None,
) -> dict[str, Any]:
    """Factory creating state transition node functions with injected agents."""
    ext_agent = extractor or ExtractorAgent(settings=settings)
    ana_agent = analyst or ContextAnalystAgent(settings=settings)
    rep_agent = reporter or ReporterAgent(settings=settings)

    async def extractor_node(state: AgentGraphState) -> dict[str, Any]:
        logger.info("Executing ExtractorNode for target: %s", state["target"])
        try:
            extraction_result = await ext_agent.extract(state["target"])
            tokens = estimate_token_count(str(extraction_result.model_dump()))
            return {
                "extraction_result": extraction_result,
                "token_count": state.get("token_count", 0) + tokens,
                "step": "extracted",
            }
        except Exception as exc:
            logger.error("ExtractorNode error: %s", exc)
            return {
                "errors": [f"Extraction failed: {exc}"],
                "step": "extracted",
            }

    async def analyst_node(state: AgentGraphState) -> dict[str, Any]:
        logger.info("Executing AnalystNode for target: %s", state["target"])
        extraction_result = state.get("extraction_result")
        if not extraction_result:
            return {
                "errors": ["AnalystNode received empty extraction result."],
                "step": "analyzed",
            }

        try:
            analysis_result = ana_agent.analyze(extraction_result)
            tokens = estimate_token_count(str(analysis_result.model_dump()))
            return {
                "analysis_result": analysis_result,
                "token_count": state.get("token_count", 0) + tokens,
                "step": "analyzed",
            }
        except Exception as exc:
            logger.error("AnalystNode error: %s", exc)
            return {
                "errors": [f"Analysis failed: {exc}"],
                "step": "analyzed",
            }

    async def reporter_node(state: AgentGraphState) -> dict[str, Any]:
        logger.info("Executing ReporterNode for target: %s", state["target"])
        extraction_result = state.get("extraction_result")
        analysis_result = state.get("analysis_result")

        if not extraction_result or not analysis_result:
            return {
                "errors": ["ReporterNode missing prerequisite extraction or analysis state."],
                "step": "reported",
                "is_finished": True,
            }

        try:
            metadata = {
                "iterations": state.get("iteration_count", 0),
                "total_estimated_tokens": state.get("token_count", 0),
            }
            report = rep_agent.generate_report(
                extraction=extraction_result,
                analysis=analysis_result,
                execution_metadata=metadata,
            )
            tokens = estimate_token_count(report.to_markdown())
            return {
                "final_report": report,
                "token_count": state.get("token_count", 0) + tokens,
                "step": "reported",
                "is_finished": True,
            }
        except Exception as exc:
            logger.error("ReporterNode error: %s", exc)
            return {
                "errors": [f"Reporting failed: {exc}"],
                "step": "reported",
                "is_finished": True,
            }

    async def supervisor_node(state: AgentGraphState) -> dict[str, Any]:
        current_iter = state.get("iteration_count", 0) + 1
        logger.debug("SupervisorNode iteration %d", current_iter)
        return {"iteration_count": current_iter}

    return {
        "extractor": extractor_node,
        "analyst": analyst_node,
        "reporter": reporter_node,
        "supervisor": supervisor_node,
    }


def compile_threat_intel_graph(
    settings: Settings | None = None,
    extractor: ExtractorAgent | None = None,
    analyst: ContextAnalystAgent | None = None,
    reporter: ReporterAgent | None = None,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the multi-agent LangGraph workflow."""
    cfg = settings or get_settings()
    nodes = create_nodes(
        settings=cfg,
        extractor=extractor,
        analyst=analyst,
        reporter=reporter,
    )

    workflow = StateGraph(AgentGraphState)

    # Register nodes
    workflow.add_node("supervisor", nodes["supervisor"])
    workflow.add_node("extractor", nodes["extractor"])
    workflow.add_node("analyst", nodes["analyst"])
    workflow.add_node("reporter", nodes["reporter"])

    # Entry point is supervisor
    workflow.set_entry_point("supervisor")

    # Conditional routing from supervisor
    workflow.add_conditional_edges(
        "supervisor",
        lambda state: supervisor_router(state, settings=cfg),
        {
            "extractor": "extractor",
            "analyst": "analyst",
            "reporter": "reporter",
            END: END,
        },
    )

    # Workers loop back to supervisor
    workflow.add_edge("extractor", "supervisor")
    workflow.add_edge("analyst", "supervisor")
    workflow.add_edge("reporter", "supervisor")

    return workflow.compile()


async def analyze_threat_async(
    target: str,
    settings: Settings | None = None,
    graph: CompiledStateGraph | None = None,  # type: ignore[type-arg]
) -> ThreatReport:
    """Execute autonomous multi-agent analysis on a target indicator or CVE."""
    cfg = settings or get_settings()
    compiled_graph = graph or compile_threat_intel_graph(settings=cfg)

    initial_state: AgentGraphState = {
        "target": target.strip(),
        "extraction_result": None,
        "analysis_result": None,
        "final_report": None,
        "errors": [],
        "iteration_count": 0,
        "token_count": 0,
        "step": "start",
        "is_finished": False,
    }

    start_time = time.perf_counter()
    logger.info("Executing threat intelligence graph for target '%s'", target)

    final_state = await compiled_graph.ainvoke(initial_state)
    elapsed = time.perf_counter() - start_time

    report = final_state.get("final_report")
    if not report:
        errors_str = "; ".join(final_state.get("errors", ["Unknown pipeline failure"]))
        raise RuntimeError(f"Workflow terminated without generating report: {errors_str}")

    logger.info(
        "Workflow finished in %.2fs. Report ID: %s | Severity: %s | Score: %.1f",
        elapsed,
        report.report_id,
        report.severity_level,
        report.risk_score,
    )
    assert isinstance(report, ThreatReport)
    return report


def analyze_threat(
    target: str,
    settings: Settings | None = None,
) -> ThreatReport:
    """Synchronous convenience wrapper around analyze_threat_async."""
    return asyncio.run(analyze_threat_async(target, settings=settings))
