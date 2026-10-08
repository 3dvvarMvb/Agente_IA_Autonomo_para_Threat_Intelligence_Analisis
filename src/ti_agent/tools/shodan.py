"""Shodan API asynchronous client."""


from ti_agent.core.config import Settings, get_settings
from ti_agent.core.exceptions import AuthenticationError, ResourceNotFoundError
from ti_agent.core.logging import get_logger
from ti_agent.models.indicator import IndicatorType, ParsedIndicator
from ti_agent.models.shodan import ShodanData
from ti_agent.tools.base import BaseApiClient

logger = get_logger("ti_agent.tools.shodan")


class ShodanClient(BaseApiClient):
    """Client for querying Shodan Internet intelligence API."""

    BASE_URL = "https://api.shodan.io"

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        interval = 0.01 if (cfg.offline_mode or not cfg.enable_cache) else 1.0
        super().__init__(
            provider_name="shodan",
            settings=cfg,
            min_request_interval=interval,
        )

    def _get_api_key(self) -> str:
        key = self.settings.shodan_api_key
        if not key and not self.settings.offline_mode:
            raise AuthenticationError(
                "Shodan API key is not configured. Set SHODAN_API_KEY or use --offline mode.",
                provider="shodan",
            )
        return key or "mock-offline-key"

    async def get_host(self, ip: str) -> ShodanData:
        """Fetch Shodan host profile (open ports, banners, vulnerabilities)."""
        url = f"{self.BASE_URL}/shodan/host/{ip}"
        params = {"key": self._get_api_key()}

        try:
            data = await self.get_json(
                url=url,
                params=params,
                fixture_fallback="shodan_ip",
            )
        except ResourceNotFoundError:
            logger.info("Host %s not indexed in Shodan database.", ip)
            return ShodanData(ip=ip, ports=[], hostnames=[])

        return ShodanData.from_api_response(ip=ip, raw_json=data)

    async def resolve_domain(self, domain: str) -> list[str]:
        """Resolve domain name to IP addresses using Shodan DNS API."""
        url = f"{self.BASE_URL}/dns/resolve"
        params = {"key": self._get_api_key(), "hostnames": domain}
        data = await self.get_json(url=url, params=params)

        # Expected response: {"example.com": "93.184.216.34"}
        if isinstance(data, dict):
            resolved_ip = data.get(domain)
            if resolved_ip:
                return [str(resolved_ip)]
        return []

    async def lookup(self, indicator: ParsedIndicator) -> ShodanData | None:
        """Dispatch query according to indicator type."""
        if indicator.type == IndicatorType.IP:
            return await self.get_host(indicator.value)

        elif indicator.type == IndicatorType.DOMAIN:
            try:
                ips = await self.resolve_domain(indicator.value)
                if ips:
                    logger.info("Resolved domain %s to %s for Shodan lookup", indicator.value, ips[0])
                    return await self.get_host(ips[0])
            except Exception as exc:
                logger.warning("Failed to resolve domain %s on Shodan: %s", indicator.value, exc)
            return None

        elif indicator.type in (IndicatorType.CVE, IndicatorType.HASH_MD5, IndicatorType.HASH_SHA1, IndicatorType.HASH_SHA256):
            logger.debug("Shodan host lookup not directly applicable for %s; skipping.", indicator.type.value)
            return None

        return None
