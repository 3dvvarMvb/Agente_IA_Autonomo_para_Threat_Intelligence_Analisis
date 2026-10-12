"""Unit and integration tests for the multi-agent LangGraph workflow and router."""

from unittest.mock import AsyncMock

import pytest
from langgraph.graph import END

from ti_agent.agents.extractor import ExtractorAgent
from ti_agent.core.config import Settings
from ti_agent.graph.router import supervisor_router
from ti_agent.graph.state import AgentGraphState
from ti_agent.graph.workflow import (
    analyze_threat_async,
    compile_threat_intel_graph,
)
from ti_agent.models.indicator import IndicatorType
from ti_agent.tools.shodan import ShodanClient


class TestSupervisorRouter:
    """Test routing transitions and execution bounds."""

    def test_sequential_transitions(self) -> None:
        cfg = Settings(max_iterations=10, max_tokens_per_execution=50000)

        # 1. Start -> Extractor
        state_start: AgentGraphState = {
            "target": "8.8.8.8",
            "extraction_result": None,
            "analysis_result": None,
            "final_report": None,
            "errors": [],
            "iteration_count": 0,
            "token_count": 100,
            "step": "start",
            "is_finished": False,
        }
        assert supervisor_router(state_start, settings=cfg) == "extractor"

        # 2. Extracted -> Analyst
        state_ext: AgentGraphState = {**state_start, "step": "extracted"}
        assert supervisor_router(state_ext, settings=cfg) == "analyst"

        # 3. Analyzed -> Reporter
        state_ana: AgentGraphState = {**state_start, "step": "analyzed"}
        assert supervisor_router(state_ana, settings=cfg) == "reporter"

        # 4. Reported -> END
        state_rep: AgentGraphState = {**state_start, "step": "reported"}
        assert supervisor_router(state_rep, settings=cfg) == END

    def test_iteration_guard_limit(self) -> None:
        cfg = Settings(max_iterations=5, max_tokens_per_execution=50000)
        state_limit: AgentGraphState = {
            "target": "8.8.8.8",
            "extraction_result": None,
            "analysis_result": None,
            "final_report": None,
            "errors": [],
            "iteration_count": 5,
            "token_count": 100,
            "step": "extractor",
            "is_finished": False,
        }
        assert supervisor_router(state_limit, settings=cfg) == END

    def test_token_budget_limit(self) -> None:
        cfg = Settings(max_iterations=10, max_tokens_per_execution=1000)
        state_token_limit: AgentGraphState = {
            "target": "8.8.8.8",
            "extraction_result": None,
            "analysis_result": None,
            "final_report": None,
            "errors": [],
            "iteration_count": 1,
            "token_count": 1500,
            "step": "extractor",
            "is_finished": False,
        }
        assert supervisor_router(state_token_limit, settings=cfg) == END


class TestWorkflowExecution:
    """Test full multi-agent graph compilation and end-to-end execution."""

    @pytest.mark.asyncio
    async def test_compile_graph(self) -> None:
        settings = Settings(offline_mode=True, enable_cache=False)
        graph = compile_threat_intel_graph(settings=settings)
        assert graph is not None

    @pytest.mark.asyncio
    async def test_e2e_cve_analysis(self) -> None:
        settings = Settings(offline_mode=True, enable_cache=False)
        report = await analyze_threat_async("CVE-2021-44228", settings=settings)

        assert report.target == "CVE-2021-44228"
        assert report.target_type == IndicatorType.CVE
        assert report.severity_level in ("HIGH", "CRITICAL")
        assert report.risk_score >= 8.0
        assert "CVE-2021-44228" in report.correlated_cves
        assert any(t.technique_id == "T1190" for t in report.mitre_techniques)
        assert len(report.mitigations) > 0
        assert report.execution_metadata.get("iterations", 0) > 0

    @pytest.mark.asyncio
    async def test_e2e_ip_analysis(self) -> None:
        settings = Settings(offline_mode=True, enable_cache=False)
        report = await analyze_threat_async("8.8.8.8", settings=settings)

        assert report.target == "8.8.8.8"
        assert report.target_type == IndicatorType.IP
        assert "Shodan Attack Surface" in report.technical_evidence
        assert any(t.technique_id == "T1046" for t in report.mitre_techniques)

    @pytest.mark.asyncio
    async def test_e2e_degraded_provider_resilience(self) -> None:
        settings = Settings(offline_mode=True, enable_cache=False)

        # Create mock Shodan client that simulates network failure
        mock_shodan = ShodanClient(settings=settings)
        mock_shodan.lookup = AsyncMock(side_effect=RuntimeError("Shodan API unreachable 503"))  # type: ignore[method-assign]

        extractor = ExtractorAgent(settings=settings, shodan_client=mock_shodan)
        graph = compile_threat_intel_graph(settings=settings, extractor=extractor)

        # Graph execution must NOT raise; it must complete gracefully in degraded mode
        report = await analyze_threat_async("8.8.8.8", settings=settings, graph=graph)

        assert report.target == "8.8.8.8"
        assert report.execution_metadata.get("degraded_mode") is True
        assert "shodan" in report.execution_metadata.get("failed_providers", [])
        assert "virustotal" in report.execution_metadata.get("successful_providers", [])
