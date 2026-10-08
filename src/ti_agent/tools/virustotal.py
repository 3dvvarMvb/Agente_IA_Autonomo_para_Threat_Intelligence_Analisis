"""VirusTotal API v3 asynchronous client."""


from ti_agent.core.config import Settings, get_settings
from ti_agent.core.exceptions import AuthenticationError
from ti_agent.core.logging import get_logger
from ti_agent.models.indicator import IndicatorType, ParsedIndicator
from ti_agent.models.virustotal import VirusTotalData
from ti_agent.tools.base import BaseApiClient

logger = get_logger("ti_agent.tools.virustotal")


class VirusTotalClient(BaseApiClient):
    """Client for querying VirusTotal v3 REST API."""

    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        # Free tier is 4 requests/minute (~15s interval). In test/offline mode use 0.01s.
        interval = 0.01 if (cfg.offline_mode or not cfg.enable_cache) else 15.0
        super().__init__(
            provider_name="virustotal",
            settings=cfg,
            min_request_interval=interval,
        )

    def _get_headers(self) -> dict[str, str]:
        key = self.settings.vt_api_key
        if not key and not self.settings.offline_mode:
            raise AuthenticationError(
                "VirusTotal API key is not configured. Set VT_API_KEY or use --offline mode.",
                provider="virustotal",
            )
        return {
            "x-apikey": key or "mock-offline-key",
            "Accept": "application/json",
        }

    async def get_ip_report(self, ip: str) -> VirusTotalData:
        """Fetch threat intelligence analysis for an IP address."""
        url = f"{self.BASE_URL}/ip_addresses/{ip}"
        data = await self.get_json(
            url=url,
            headers=self._get_headers(),
            fixture_fallback="virustotal_ip",
        )
        return VirusTotalData.from_api_response(target=ip, target_type="ip", raw_json=data)

    async def get_domain_report(self, domain: str) -> VirusTotalData:
        """Fetch threat intelligence analysis for a domain name."""
        url = f"{self.BASE_URL}/domains/{domain}"
        data = await self.get_json(
            url=url,
            headers=self._get_headers(),
            fixture_fallback="virustotal_domain",
        )
        return VirusTotalData.from_api_response(
            target=domain, target_type="domain", raw_json=data
        )

    async def get_file_report(self, file_hash: str) -> VirusTotalData:
        """Fetch threat intelligence analysis for an MD5, SHA1, or SHA256 file hash."""
        url = f"{self.BASE_URL}/files/{file_hash}"
        data = await self.get_json(
            url=url,
            headers=self._get_headers(),
            fixture_fallback="virustotal_hash",
        )
        return VirusTotalData.from_api_response(
            target=file_hash, target_type="hash", raw_json=data
        )

    async def lookup(self, indicator: ParsedIndicator) -> VirusTotalData | None:
        """Dispatch query according to indicator type."""
        if indicator.type == IndicatorType.IP:
            return await self.get_ip_report(indicator.value)
        elif indicator.type == IndicatorType.DOMAIN:
            return await self.get_domain_report(indicator.value)
        elif indicator.type.is_hash:
            return await self.get_file_report(indicator.value)
        elif indicator.type == IndicatorType.CVE:
            logger.debug("VirusTotal does not support direct CVE lookups; skipping.")
            return None
        return None
