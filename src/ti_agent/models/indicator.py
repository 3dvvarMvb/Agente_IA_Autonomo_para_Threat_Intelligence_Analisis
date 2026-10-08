"""Indicator identification, validation, and normalization models."""

import ipaddress
import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ti_agent.core.exceptions import IndicatorValidationError

# Regex definitions for deterministic parsing
DOMAIN_REGEX = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)
MD5_REGEX = re.compile(r"^[a-fA-F0-9]{32}$")
SHA1_REGEX = re.compile(r"^[a-fA-F0-9]{40}$")
SHA256_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")
CVE_REGEX = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)


class IndicatorType(StrEnum):
    """Supported types of Indicators of Compromise (IoC) and vulnerabilities."""

    IP = "ip"
    DOMAIN = "domain"
    HASH_MD5 = "hash_md5"
    HASH_SHA1 = "hash_sha1"
    HASH_SHA256 = "hash_sha256"
    CVE = "cve"

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

    @classmethod
    def parse(cls, target: str) -> "ParsedIndicator":
        """Parse, validate, and normalize a target indicator or CVE string.

        Args:
            target: Input string (IP, domain, hash, or CVE-ID).

        Returns:
            ParsedIndicator instance with normalized value.

        Raises:
            IndicatorValidationError: If target cannot be recognized or validated.
        """
        raw = target.strip()
        if not raw:
            raise IndicatorValidationError("Target indicator cannot be empty.")

        # 1. Check CVE format
        if CVE_REGEX.match(raw):
            return cls(raw_value=target, value=raw.upper(), type=IndicatorType.CVE)

        # 2. Check IP address (IPv4 and IPv6)
        try:
            ip_obj = ipaddress.ip_address(raw)
            return cls(raw_value=target, value=str(ip_obj), type=IndicatorType.IP)
        except ValueError:
            pass

        # 3. Check cryptographic hashes (case-insensitive hex)
        if SHA256_REGEX.match(raw):
            return cls(raw_value=target, value=raw.lower(), type=IndicatorType.HASH_SHA256)
        if SHA1_REGEX.match(raw):
            return cls(raw_value=target, value=raw.lower(), type=IndicatorType.HASH_SHA1)
        if MD5_REGEX.match(raw):
            return cls(raw_value=target, value=raw.lower(), type=IndicatorType.HASH_MD5)

        # 4. Check domain name (clean any protocol prefix if mistakenly passed)
        cleaned_domain = re.sub(r"^https?://", "", raw).split("/")[0].split(":")[0]
        if DOMAIN_REGEX.match(cleaned_domain):
            return cls(raw_value=target, value=cleaned_domain.lower(), type=IndicatorType.DOMAIN)

        raise IndicatorValidationError(
            f"Unable to recognize indicator format: '{target}'. "
            "Supported formats: IPv4/IPv6, Domain, MD5, SHA1, SHA256, or CVE (e.g., CVE-2021-44228)."
        )
