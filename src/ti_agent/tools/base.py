"""Base asynchronous HTTP client with retries, caching, rate-limiting, and offline fixture support."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import diskcache
import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.exceptions import (
    APIClientError,
    AuthenticationError,
    ProviderUnavailableError,
    RateLimitExceededError,
    ResourceNotFoundError,
)
from ti_agent.core.logging import get_logger

logger = get_logger("ti_agent.tools.base")


class BaseApiClient:
    """Resilient async HTTP client for external threat intelligence providers."""

    def __init__(
        self,
        provider_name: str,
        settings: Settings | None = None,
        min_request_interval: float = 0.5,
    ) -> None:
        self.provider_name = provider_name
        self.settings = settings or get_settings()
        self.min_request_interval = min_request_interval
        self._last_request_time: float = 0.0
        self._rate_limit_lock = asyncio.Lock()

        # Cache initialization
        self.cache: diskcache.Cache | None = None
        if self.settings.enable_cache:
            cache_path = self.settings.cache_dir / self.provider_name
            cache_path.mkdir(parents=True, exist_ok=True)
            self.cache = diskcache.Cache(str(cache_path))

    async def _enforce_rate_limit(self) -> None:
        """Enforce inter-request rate limiting to respect free-tier quotas."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.min_request_interval:
                sleep_needed = self.min_request_interval - elapsed
                logger.debug(
                    "Rate limit guard: sleeping %.2fs for %s", sleep_needed, self.provider_name
                )
                await asyncio.sleep(sleep_needed)
            self._last_request_time = time.monotonic()

    def _get_cache_key(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        param_str = json.dumps(params or {}, sort_keys=True)
        return f"{endpoint}:{param_str}"

    def _load_offline_fixture(self, fixture_name: str) -> dict[str, Any] | None:
        """Attempt to load mock data from fixtures directory for offline demo/testing."""
        fixture_paths = [
            Path("fixtures") / f"{fixture_name}.json",
            Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / f"{fixture_name}.json",
        ]
        for p in fixture_paths:
            if p.is_file():
                try:
                    with open(p, encoding="utf-8") as f:
                        return json.load(f)  # type: ignore[no-any-return]
                except Exception as exc:
                    logger.warning("Failed to parse fixture %s: %s", p, exc)
        return None

    async def _execute_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute HTTP request with Tenacity exponential backoff and jitter."""
        is_fast_mode = self.settings.offline_mode or not self.settings.enable_cache
        wait_strategy = (
            wait_exponential_jitter(multiplier=0.01, max=0.05)
            if is_fast_mode
            else wait_exponential_jitter(multiplier=1, max=10)
        )

        retryer = AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_strategy,
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        )

        async for attempt in retryer:
            with attempt:
                await self._enforce_rate_limit()
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    timeout=httpx.Timeout(15.0, connect=5.0),
                )

                if response.status_code == 429:
                    logger.warning(
                        "Rate limit (429) hit on %s. Attempt %d/3.",
                        self.provider_name,
                        attempt.retry_state.attempt_number,
                    )
                    # Retry on 429 if attempts remain
                    if attempt.retry_state.attempt_number < 3:
                        sleep_time = 0.01 if is_fast_mode else (2.0 * attempt.retry_state.attempt_number)
                        await asyncio.sleep(sleep_time)
                        raise httpx.TimeoutException(f"429 Rate limited by {self.provider_name}")
                    raise RateLimitExceededError(
                        f"Rate limit exceeded on {self.provider_name}",
                        provider=self.provider_name,
                        status_code=429,
                    )

                if response.status_code in (500, 502, 503, 504):
                    logger.warning(
                        "Server error (%d) from %s. Attempt %d/3.",
                        response.status_code,
                        self.provider_name,
                        attempt.retry_state.attempt_number,
                    )
                    if attempt.retry_state.attempt_number < 3:
                        raise httpx.TimeoutException(f"Server error {response.status_code}")
                    raise ProviderUnavailableError(
                        f"{self.provider_name} returned server error {response.status_code}",
                        provider=self.provider_name,
                        status_code=response.status_code,
                    )

                return response

        raise ProviderUnavailableError(
            f"Exhausted retries connecting to {self.provider_name}",
            provider=self.provider_name,
        )

    async def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        fixture_fallback: str | None = None,
    ) -> dict[str, Any]:
        """Fetch JSON payload with offline mode, caching, and error handling."""
        # 1. Offline Mode check
        if self.settings.offline_mode and fixture_fallback:
            logger.info(
                "Offline mode active: loading fixture '%s' for %s",
                fixture_fallback,
                self.provider_name,
            )
            fixture = self._load_offline_fixture(fixture_fallback)
            if fixture is not None:
                return fixture
            logger.warning("Fixture '%s' not found in offline mode.", fixture_fallback)

        # 2. Check Cache
        cache_key = self._get_cache_key(url, params)
        if self.cache is not None:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                logger.debug("Cache hit for %s: %s", self.provider_name, url)
                return cached_data  # type: ignore[no-any-return]

        # 3. Network Request
        async with httpx.AsyncClient() as client:
            try:
                resp = await self._execute_with_retry(
                    client=client,
                    method="GET",
                    url=url,
                    headers=headers,
                    params=params,
                )
            except (RateLimitExceededError, ProviderUnavailableError):
                raise
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError(
                    f"HTTP communication error with {self.provider_name}: {exc}",
                    provider=self.provider_name,
                ) from exc

        # 4. Handle HTTP Status codes
        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed on {self.provider_name} (HTTP {resp.status_code}). Check API key.",
                provider=self.provider_name,
                status_code=resp.status_code,
            )

        if resp.status_code == 404:
            raise ResourceNotFoundError(
                f"Indicator not found on {self.provider_name} (HTTP 404).",
                provider=self.provider_name,
                status_code=404,
            )

        if resp.status_code >= 400:
            raise APIClientError(
                f"Client error from {self.provider_name} (HTTP {resp.status_code}): {resp.text[:200]}",
                provider=self.provider_name,
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise APIClientError(
                f"Failed to parse JSON response from {self.provider_name}",
                provider=self.provider_name,
            ) from exc

        # 5. Persist to cache
        if self.cache is not None and isinstance(data, dict):
            self.cache.set(cache_key, data, expire=self.settings.cache_ttl_seconds)

        return data  # type: ignore[no-any-return]
