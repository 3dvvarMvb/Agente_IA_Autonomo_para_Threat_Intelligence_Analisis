"""Indicator identification, validation, and normalization models."""

import ipaddress
import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ti_agent.core.exceptions import IndicatorValidationError

# Regex definitions for deterministic parsing
DOMAIN_REGEX = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")
MD5_REGEX = re.compile(r"^[a-fA-F0-9]{32}$")
SHA1_REGEX = re.compile(r"^[a-fA-F0-9]{40}$")
SHA256_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")
CVE_REGEX = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)


class IndicatorType(StrEnum):
    """Supported types of Indicators of Compromise (IoC), vulnerabilities, and web targets."""

    IP = "ip"
    DOMAIN = "domain"
    HASH_MD5 = "hash_md5"
    HASH_SHA1 = "hash_sha1"
    HASH_SHA256 = "hash_sha256"
    CVE = "cve"
    URL = "url"

    @property
    def is_hash(self) -> bool:
        """Return True if the indicator is a file cryptographic hash."""
        return self in (
            IndicatorType.HASH_MD5,
            IndicatorType.HASH_SHA1,
            IndicatorType.HASH_SHA256,
        )


class ParsedIndicator(BaseModel):
    """Normalized and validated indicator representation."""

    model_config = ConfigDict(frozen=True)

    raw_value: str = Field(description="Original unformatted user input string")
    value: str = Field(description="Normalized canonical value")
    type: IndicatorType = Field(description="Detected indicator type")

    @property
    def is_local_target(self) -> bool:
        """Check if indicator points to localhost, loopback, or private network."""
        if self.type == IndicatorType.URL:
            from urllib.parse import urlparse

            hostname = (urlparse(self.value).hostname or "").lower()
            if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
                return True
            try:
                ip = ipaddress.ip_address(hostname)
                return ip.is_loopback or ip.is_private
            except ValueError:
                return False
        elif self.type == IndicatorType.IP:
            try:
                ip = ipaddress.ip_address(self.value)
                return ip.is_loopback or ip.is_private
            except ValueError:
                return False
        elif self.type == IndicatorType.DOMAIN:
            return self.value.lower() in ("localhost", "local", "127.0.0.1")
        return False

    @property
    def url_host(self) -> str | None:
        """Extract hostname if indicator is a URL."""
        if self.type == IndicatorType.URL:
            from urllib.parse import urlparse

            return urlparse(self.value).hostname
        return None

    @property
    def url_port(self) -> int | None:
        """Extract port if indicator is a URL."""
        if self.type == IndicatorType.URL:
            from urllib.parse import urlparse

            parsed = urlparse(self.value)
            if parsed.port:
                return parsed.port
            return 443 if parsed.scheme == "https" else 80
        return None

    @classmethod
    def parse(cls, target: str) -> "ParsedIndicator":
        """Parse, validate, and normalize a target indicator, URL, or CVE string.

        Args:
            target: Input string (IP, domain, hash, URL, or CVE-ID).

        Returns:
            ParsedIndicator instance with normalized value.

        Raises:
            IndicatorValidationError: If target cannot be recognized or validated.
        """
        raw = target.strip()
        if not raw:
            raise IndicatorValidationError("Target indicator cannot be empty.")

        # 1. Check Web URL format (e.g. http://localhost:8080/dashboard or https://example.com)
        if raw.lower().startswith(("http://", "https://")):
            from urllib.parse import urlparse

            parsed = urlparse(raw)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return cls(raw_value=target, value=raw, type=IndicatorType.URL)
            raise IndicatorValidationError(f"Invalid web URL format: '{target}'.")

        # 2. Check CVE format
        if CVE_REGEX.match(raw):
            return cls(raw_value=target, value=raw.upper(), type=IndicatorType.CVE)

        # 3. Check IP address (IPv4 and IPv6)
        try:
            ip_obj = ipaddress.ip_address(raw)
            return cls(raw_value=target, value=str(ip_obj), type=IndicatorType.IP)
        except ValueError:
            pass

        # 4. Check cryptographic hashes (case-insensitive hex)
        if SHA256_REGEX.match(raw):
            return cls(raw_value=target, value=raw.lower(), type=IndicatorType.HASH_SHA256)
        if SHA1_REGEX.match(raw):
            return cls(raw_value=target, value=raw.lower(), type=IndicatorType.HASH_SHA1)
        if MD5_REGEX.match(raw):
            return cls(raw_value=target, value=raw.lower(), type=IndicatorType.HASH_MD5)

        # 5. Check domain name
        if DOMAIN_REGEX.match(raw):
            return cls(raw_value=target, value=raw.lower(), type=IndicatorType.DOMAIN)

        raise IndicatorValidationError(
            f"Unable to recognize indicator format: '{target}'. "
            "Supported formats: Web URL (http/https), IPv4/IPv6, Domain, MD5, SHA1, SHA256, or CVE."
        )
