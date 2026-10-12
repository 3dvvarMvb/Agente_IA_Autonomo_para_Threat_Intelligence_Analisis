"""NIST National Vulnerability Database (NVD) API 2.0 asynchronous client."""

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.logging import get_logger
from ti_agent.models.indicator import IndicatorType, ParsedIndicator
from ti_agent.models.nvd import NvdCveData
from ti_agent.tools.base import BaseApiClient

logger = get_logger("ti_agent.tools.nvd")


class NvdClient(BaseApiClient):
    """Client for querying NIST NVD API 2.0 vulnerability database."""

    BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        # Rate limit: 0.6s with key (50 req/30s), 6.0s without key (5 req/30s)
        if cfg.offline_mode or not cfg.enable_cache:
            interval = 0.01
        elif cfg.nvd_api_key:
            interval = 0.6
        else:
            interval = 6.0

        super().__init__(
            provider_name="nvd",
            settings=cfg,
            min_request_interval=interval,
        )

    def _get_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.settings.nvd_api_key:
            headers["apiKey"] = self.settings.nvd_api_key
        return headers

    async def get_cve(self, cve_id: str) -> NvdCveData:
        """Fetch CVE vulnerability profile from NIST NVD 2.0."""
        normalized_cve = cve_id.strip().upper()
        params = {"cveId": normalized_cve}

        data = await self.get_json(
            url=self.BASE_URL,
            headers=self._get_headers(),
            params=params,
            fixture_fallback="nvd_cve",
        )
        return NvdCveData.from_api_response(raw_json=data)

    async def lookup(self, indicator: ParsedIndicator) -> NvdCveData | None:
        """Dispatch query if indicator is a CVE identifier."""
        if indicator.type == IndicatorType.CVE:
            return await self.get_cve(indicator.value)
        return None
