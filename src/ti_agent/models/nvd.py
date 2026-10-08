"""Normalized Pydantic models for NIST NVD API 2.0 vulnerability data."""

import contextlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NvdCvssMetrics(BaseModel):
    """CVSS version 3.x vulnerability metrics."""

    model_config = ConfigDict(frozen=True)

    version: str = Field(default="3.1")
    base_score: float = Field(ge=0.0, le=10.0, description="CVSS base numerical score")
    base_severity: str = Field(description="CVSS base severity string (e.g., CRITICAL, HIGH)")
    vector_string: str = Field(description="Standard CVSS vector string")
    exploitability_score: float | None = Field(default=None, ge=0.0, le=10.0)
    impact_score: float | None = Field(default=None, ge=0.0, le=10.0)


class NvdCveData(BaseModel):
    """Normalized vulnerability intelligence extracted from NIST NVD 2.0."""

    model_config = ConfigDict(frozen=True)

    cve_id: str = Field(description="Unique CVE identifier (e.g. CVE-2021-44228)")
    description: str = Field(description="Official English vulnerability description")
    published_date: datetime | None = Field(default=None)
    last_modified_date: datetime | None = Field(default=None)
    cvss: NvdCvssMetrics | None = Field(default=None, description="Primary CVSS metrics")
    cwe_ids: list[str] = Field(default_factory=list, description="Associated CWE identifiers")
    affected_cpes: list[str] = Field(
        default_factory=list, description="Sample of affected CPE criteria"
    )
    references: list[str] = Field(default_factory=list, description="Advisory reference URLs")

    @property
    def severity(self) -> str:
        """Returns uppercase severity level (CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN)."""
        if self.cvss and self.cvss.base_severity:
            return self.cvss.base_severity.upper()
        return "UNKNOWN"

    @property
    def score(self) -> float:
        """Returns CVSS score or 0.0 if not scored."""
        return self.cvss.base_score if self.cvss else 0.0

    @classmethod
    def from_api_response(cls, raw_json: dict[str, Any]) -> "NvdCveData":
        """Factory method to parse NIST NVD 2.0 API response into normalized model."""
        vulnerabilities = raw_json.get("vulnerabilities", [])
        if not vulnerabilities:
            raise ValueError("NVD response contains no vulnerabilities.")

        item = vulnerabilities[0]
        cve_node = item.get("cve", {})
        cve_id = cve_node.get("id", "UNKNOWN-CVE").upper()

        # Extract English description
        descriptions = cve_node.get("descriptions", [])
        desc_text = "No description available."
        for d in descriptions:
            if d.get("lang") == "en":
                desc_text = d.get("value", desc_text)
                break

        # Dates
        pub_str = cve_node.get("published")
        pub_dt = None
        if pub_str:
            with contextlib.suppress(ValueError):
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))

        mod_str = cve_node.get("lastModified")
        mod_dt = None
        if mod_str:
            with contextlib.suppress(ValueError):
                mod_dt = datetime.fromisoformat(mod_str.replace("Z", "+00:00"))

        # Parse CVSS Metrics (check v31, then v30)
        metrics = cve_node.get("metrics", {})
        cvss_list = metrics.get("cvssMetricV31", []) or metrics.get("cvssMetricV30", [])

        cvss_model: NvdCvssMetrics | None = None
        if cvss_list:
            # Find primary source metric or take first
            primary_metric = next(
                (m for m in cvss_list if m.get("type", "").lower() == "primary"),
                cvss_list[0],
            )
            cvss_data = primary_metric.get("cvssData", {})
            if "baseScore" in cvss_data:
                cvss_model = NvdCvssMetrics(
                    version=str(cvss_data.get("version", "3.1")),
                    base_score=float(cvss_data.get("baseScore", 0.0)),
                    base_severity=str(cvss_data.get("baseSeverity", "UNKNOWN")),
                    vector_string=str(cvss_data.get("vectorString", "")),
                    exploitability_score=primary_metric.get("exploitabilityScore"),
                    impact_score=primary_metric.get("impactScore"),
                )

        # Parse CWEs
        cwe_ids: list[str] = []
        for weakness in cve_node.get("weaknesses", []):
            for desc in weakness.get("description", []):
                val = desc.get("value")
                if val and val not in ("NVD-CWE-noinfo", "NVD-CWE-Other") and val not in cwe_ids:
                    cwe_ids.append(val)

        # Parse CPEs (limit to top 10 for compact representation)
        affected_cpes: list[str] = []
        for cfg in cve_node.get("configurations", []):
            for node in cfg.get("nodes", []):
                for match in node.get("cpeMatch", []):
                    criteria = match.get("criteria")
                    if criteria and criteria not in affected_cpes:
                        affected_cpes.append(criteria)
                        if len(affected_cpes) >= 10:
                            break

        # References (limit to top 5)
        references: list[str] = []
        for ref in cve_node.get("references", []):
            url = ref.get("url")
            if url and url not in references:
                references.append(url)
                if len(references) >= 5:
                    break

        return cls(
            cve_id=cve_id,
            description=desc_text,
            published_date=pub_dt,
            last_modified_date=mod_dt,
            cvss=cvss_model,
            cwe_ids=cwe_ids,
            affected_cpes=affected_cpes,
            references=references,
        )
