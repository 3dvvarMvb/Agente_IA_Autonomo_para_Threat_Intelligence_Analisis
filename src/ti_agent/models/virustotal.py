"""Normalized Pydantic models for VirusTotal API v3 telemetry."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VirusTotalStats(BaseModel):
    """Aggregated analysis engine votes."""

    model_config = ConfigDict(frozen=True)

    malicious: int = Field(default=0, ge=0)
    suspicious: int = Field(default=0, ge=0)
    harmless: int = Field(default=0, ge=0)
    undetected: int = Field(default=0, ge=0)
    timeout: int = Field(default=0, ge=0)

    @property
    def total_engines(self) -> int:
        """Total number of participating security vendors/engines."""
        return self.malicious + self.suspicious + self.harmless + self.undetected + self.timeout

    @property
    def positive_engines(self) -> int:
        """Total engines flagging the indicator as malicious or suspicious."""
        return self.malicious + self.suspicious


class VirusTotalData(BaseModel):
    """Normalized threat intelligence data extracted from VirusTotal v3."""

    model_config = ConfigDict(frozen=True)

    target: str = Field(description="Queried indicator value")
    target_type: str = Field(description="Indicator type (ip, domain, hash)")
    stats: VirusTotalStats = Field(default_factory=VirusTotalStats)
    reputation: int = Field(default=0, description="Community reputation score")
    community_tags: list[str] = Field(default_factory=list, description="Associated community tags")
    categories: dict[str, str] = Field(
        default_factory=dict, description="Categorization by vendors"
    )
    last_analysis_date: datetime | None = Field(default=None)
    as_owner: str | None = Field(default=None, description="Autonomous System Owner (for IPs)")
    country: str | None = Field(default=None, description="Country code (for IPs)")
    meaningful_name: str | None = Field(default=None, description="File name if hash queried")

    @property
    def is_flagged_malicious(self) -> bool:
        """Heuristic check: flagged if 2 or more vendors consider it malicious/suspicious."""
        return self.stats.positive_engines >= 2 or self.reputation < -5

    @property
    def detection_ratio(self) -> str:
        """Returns standard detection fraction string, e.g., '14/72'."""
        return f"{self.stats.positive_engines}/{self.stats.total_engines}"

    @classmethod
    def from_api_response(
        cls, target: str, target_type: str, raw_json: dict[str, Any]
    ) -> "VirusTotalData":
        """Factory method to transform VirusTotal v3 JSON into normalized model."""
        data = raw_json.get("data", {})
        attributes = data.get("attributes", {})

        stats_raw = attributes.get("last_analysis_stats", {})
        stats = VirusTotalStats(
            malicious=stats_raw.get("malicious", 0),
            suspicious=stats_raw.get("suspicious", 0),
            harmless=stats_raw.get("harmless", 0),
            undetected=stats_raw.get("undetected", 0),
            timeout=stats_raw.get("timeout", 0),
        )

        ts = attributes.get("last_analysis_date")
        analysis_date = datetime.fromtimestamp(ts, tz=UTC) if isinstance(ts, (int, float)) else None

        return cls(
            target=target,
            target_type=target_type,
            stats=stats,
            reputation=attributes.get("reputation", 0),
            community_tags=attributes.get("tags", []) or [],
            categories=attributes.get("categories", {}) or {},
            last_analysis_date=analysis_date,
            as_owner=attributes.get("as_owner"),
            country=attributes.get("country"),
            meaningful_name=attributes.get("meaningful_name"),
        )
