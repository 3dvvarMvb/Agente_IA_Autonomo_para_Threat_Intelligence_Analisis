"""Custom exception hierarchy for the Threat Intelligence Agent system."""

from typing import Any


class ThreatIntelError(Exception):
    """Base exception for all threat-intel-agent errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class IndicatorValidationError(ThreatIntelError):
    """Raised when an indicator or CVE string fails validation."""

    pass


class ConfigurationError(ThreatIntelError):
    """Raised when application configuration or environment variables are invalid."""

    pass


class APIClientError(ThreatIntelError):
    """Base exception for external threat intelligence API client errors."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.provider = provider
        self.status_code = status_code


class AuthenticationError(APIClientError):
    """Raised when API key is missing, unauthorized, or forbidden (HTTP 401/403)."""

    pass


class RateLimitExceededError(APIClientError):
    """Raised when provider rate limits are exhausted after retries (HTTP 429)."""

    pass


class ResourceNotFoundError(APIClientError):
    """Raised when the queried indicator or CVE is not found in the provider (HTTP 404)."""

    pass


class ProviderUnavailableError(APIClientError):
    """Raised when an external API is down, timing out, or returning server errors (HTTP 5xx)."""

    pass


class PromptInjectionDetectedError(ThreatIntelError):
    """Raised when untrusted content contains overt prompt injection patterns."""

    pass
