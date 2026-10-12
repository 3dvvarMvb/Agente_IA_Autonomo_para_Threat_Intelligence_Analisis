"""Extractor Agent: concurrently queries external feeds and normalizes telemetry into Pydantic models."""

import asyncio
import time

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.logging import get_logger
from ti_agent.models.indicator import IndicatorType, ParsedIndicator
from ti_agent.models.nvd import NvdCveData
from ti_agent.models.report import ExtractionResult, ProviderStatus
from ti_agent.models.shodan import ShodanData
from ti_agent.models.virustotal import VirusTotalData
from ti_agent.models.web_audit import WebAuditResult
from ti_agent.tools.nvd import NvdClient
from ti_agent.tools.shodan import ShodanClient
from ti_agent.tools.virustotal import VirusTotalClient
from ti_agent.tools.web_auditor import WebSecurityAuditor

logger = get_logger("ti_agent.agents.extractor")


class ExtractorAgent:
    """Agent responsible for parallel external telemetry ingestion and normalization."""

    def __init__(
        self,
        settings: Settings | None = None,
        vt_client: VirusTotalClient | None = None,
        shodan_client: ShodanClient | None = None,
        nvd_client: NvdClient | None = None,
        web_auditor: WebSecurityAuditor | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.vt_client = vt_client or VirusTotalClient(settings=self.settings)
        self.shodan_client = shodan_client or ShodanClient(settings=self.settings)
        self.nvd_client = nvd_client or NvdClient(settings=self.settings)
        self.web_auditor = web_auditor or WebSecurityAuditor(settings=self.settings)

    async def _query_virustotal(
        self, indicator: ParsedIndicator
    ) -> tuple[VirusTotalData | None, ProviderStatus]:
        start = time.perf_counter()
        try:
            data = await self.vt_client.lookup(indicator)
            elapsed = (time.perf_counter() - start) * 1000.0
            return data, ProviderStatus(
                provider="virustotal",
                success=True,
                elapsed_ms=round(elapsed, 2),
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            logger.warning("VirusTotal extraction failed for %s: %s", indicator.value, exc)
            return None, ProviderStatus(
                provider="virustotal",
                success=False,
                error_message=str(exc),
                elapsed_ms=round(elapsed, 2),
            )

    async def _query_shodan(
        self, indicator: ParsedIndicator
    ) -> tuple[ShodanData | None, ProviderStatus]:
        start = time.perf_counter()
        try:
            data = await self.shodan_client.lookup(indicator)
            elapsed = (time.perf_counter() - start) * 1000.0
            return data, ProviderStatus(
                provider="shodan",
                success=True,
                elapsed_ms=round(elapsed, 2),
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            logger.warning("Shodan extraction failed for %s: %s", indicator.value, exc)
            return None, ProviderStatus(
                provider="shodan",
                success=False,
                error_message=str(exc),
                elapsed_ms=round(elapsed, 2),
            )

    async def _query_nvd(
        self, indicator: ParsedIndicator
    ) -> tuple[NvdCveData | None, ProviderStatus]:
        start = time.perf_counter()
        try:
            data = await self.nvd_client.lookup(indicator)
            elapsed = (time.perf_counter() - start) * 1000.0
            return data, ProviderStatus(
                provider="nvd",
                success=True,
                elapsed_ms=round(elapsed, 2),
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            logger.warning("NVD extraction failed for %s: %s", indicator.value, exc)
            return None, ProviderStatus(
                provider="nvd",
                success=False,
                error_message=str(exc),
                elapsed_ms=round(elapsed, 2),
            )

    async def _query_web_auditor(
        self, indicator: ParsedIndicator
    ) -> tuple[WebAuditResult | None, ProviderStatus]:
        start = time.perf_counter()
        try:
            data = await self.web_auditor.audit_url(indicator.value)
            elapsed = (time.perf_counter() - start) * 1000.0
            return data, ProviderStatus(
                provider="web_auditor",
                success=True,
                elapsed_ms=round(elapsed, 2),
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            logger.warning("Web audit extraction failed for %s: %s", indicator.value, exc)
            return None, ProviderStatus(
                provider="web_auditor",
                success=False,
                error_message=str(exc),
                elapsed_ms=round(elapsed, 2),
            )

    async def extract(self, target: str) -> ExtractionResult:
        """Parse indicator and query all applicable feeds in parallel."""
        indicator = ParsedIndicator.parse(target)
        logger.info(
            "Starting parallel telemetry extraction for: %s (%s)",
            indicator.value,
            indicator.type.value,
        )

        # Handle Web URL targets
        if indicator.type == IndicatorType.URL:
            web_data, web_status = await self._query_web_auditor(indicator)
            vt_status = ProviderStatus(
                provider="virustotal", success=True, error_message="Skipped (Web Target)"
            )
            shodan_status = ProviderStatus(
                provider="shodan", success=True, error_message="Skipped (Web Target)"
            )
            nvd_status = ProviderStatus(
                provider="nvd", success=True, error_message="Skipped (Web Target)"
            )
            statuses = [web_status, vt_status, shodan_status, nvd_status]
            return ExtractionResult(
                indicator=indicator,
                web_audit=web_data,
                statuses=statuses,
            )

        # Run external API calls in parallel for standard IoCs and CVEs
        (
            (vt_data, vt_status),
            (shodan_data, shodan_status),
            (nvd_data, nvd_status),
        ) = await asyncio.gather(
            self._query_virustotal(indicator),
            self._query_shodan(indicator),
            self._query_nvd(indicator),
        )

        statuses = [vt_status, shodan_status, nvd_status]
        result = ExtractionResult(
            indicator=indicator,
            virustotal=vt_data,
            shodan=shodan_data,
            nvd=nvd_data,
            statuses=statuses,
        )

        logger.info(
            "Extraction complete for %s. Successful providers: %s. Degraded: %s",
            indicator.value,
            result.successful_providers,
            result.is_degraded,
        )
        return result
