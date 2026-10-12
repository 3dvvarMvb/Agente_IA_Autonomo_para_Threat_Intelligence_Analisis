"""Domain models for unified extraction results, threat findings, and technical reports."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ti_agent.models.indicator import IndicatorType, ParsedIndicator
from ti_agent.models.nvd import NvdCveData
from ti_agent.models.shodan import ShodanData
from ti_agent.models.virustotal import VirusTotalData
from ti_agent.models.web_audit import WebAuditResult


class ProviderStatus(BaseModel):
    """Execution status for an individual external threat intelligence provider."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(description="Provider name (virustotal, shodan, nvd)")
    success: bool = Field(description="Whether the query succeeded")
    error_message: str | None = Field(default=None, description="Error reason if query failed")
    elapsed_ms: float = Field(default=0.0, description="Response time in milliseconds")


class ExtractionResult(BaseModel):
    """Unified container aggregating telemetry from all external threat intelligence feeds."""

    model_config = ConfigDict(frozen=True)

    indicator: ParsedIndicator = Field(description="Normalized target indicator")
    virustotal: VirusTotalData | None = Field(
        default=None, description="VirusTotal telemetry if queried"
    )
    shodan: ShodanData | None = Field(default=None, description="Shodan telemetry if queried")
    nvd: NvdCveData | None = Field(default=None, description="NIST NVD telemetry if queried")
    web_audit: WebAuditResult | None = Field(
        default=None, description="Dynamic web application security inspection results"
    )
    statuses: list[ProviderStatus] = Field(
        default_factory=list, description="Per-provider execution results"
    )

    @property
    def is_degraded(self) -> bool:
        """True if any queried provider returned an error."""
        return any(not s.success for s in self.statuses)

    @property
    def successful_providers(self) -> list[str]:
        """List of providers that succeeded."""
        return [s.provider for s in self.statuses if s.success]

    @property
    def failed_providers(self) -> list[str]:
        """List of providers that failed."""
        return [s.provider for s in self.statuses if not s.success]


class MitreTechnique(BaseModel):
    """Mapped MITRE ATT&CK enterprise technique."""

    model_config = ConfigDict(frozen=True)

    technique_id: str = Field(description="MITRE ATT&CK ID (e.g. T1190)")
    name: str = Field(description="Technique name (e.g. Exploit Public-Facing Application)")
    tactic: str = Field(description="Tactic category (e.g. Initial Access)")
    description: str = Field(description="Brief summary of technique behavior")
    relevance_explanation: str = Field(
        description="Justification for how this technique relates to the observed telemetry"
    )


class Mitigation(BaseModel):
    """Actionable remediation or defense countermeasure."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(description="Clear mitigation action title")
    description: str = Field(description="Explanation of the mitigation mechanism")
    priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = Field(
        description="Implementation priority based on exposure and risk"
    )
    category: str = Field(
        description="Category: Patching, Network Hardening, Detection Rule, Configuration Change"
    )
    actionable_steps: list[str] = Field(
        default_factory=list, description="Concrete step-by-step instructions for engineers"
    )


class ThreatReport(BaseModel):
    """Comprehensive final technical threat intelligence analysis report."""

    model_config = ConfigDict(frozen=True)

    report_id: str = Field(
        default_factory=lambda: f"TR-{uuid.uuid4().hex[:8].upper()}",
        description="Unique report tracking identifier",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC generation timestamp",
    )
    target: str = Field(description="Target analyzed (IP, domain, hash, CVE)")
    target_type: IndicatorType = Field(description="Classified indicator type")
    executive_summary: str = Field(description="Concise C-level and SOC lead executive overview")
    severity_level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"] = Field(
        description="Overall synthesized severity level"
    )
    risk_score: float = Field(
        ge=0.0,
        le=10.0,
        description="Calculated composite risk score (0.0 - 10.0)",
    )
    risk_rationale: str = Field(
        description="Mathematical and contextual justification for the assigned risk score"
    )
    technical_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key findings extracted from telemetry feeds",
    )
    correlated_cves: list[str] = Field(
        default_factory=list,
        description="List of CVE IDs directly correlated to this indicator",
    )
    mitre_techniques: list[MitreTechnique] = Field(
        default_factory=list,
        description="Mapped MITRE ATT&CK techniques with justifications",
    )
    mitigations: list[Mitigation] = Field(
        default_factory=list,
        description="Prioritized actionable remediation recommendations",
    )
    references: list[str] = Field(
        default_factory=list,
        description="Verified reference URLs and vendor advisories",
    )
    language: Literal["es", "en"] = Field(
        default="es",
        description="Language used for the report (es/en)",
    )
    execution_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent runtime metadata: steps taken, duration, token usage",
    )

    def to_markdown(self, lang: str | None = None) -> str:
        """Render report as formatted GitHub-Flavored Markdown in specified or report language."""
        from ti_agent.core.i18n import resolve_language, t

        resolved_lang = resolve_language(lang or self.language)
        none_str = t("none_observed", lang=resolved_lang)
        cves_str = ", ".join(self.correlated_cves) if self.correlated_cves else none_str

        md = [
            f"# {t('md_report_title', lang=resolved_lang)}: {self.target}",
            f"**{t('md_report_id', lang=resolved_lang)}:** `{self.report_id}` | **{t('md_generated', lang=resolved_lang)}:** `{self.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}`",
            f"**{t('md_indicator_type', lang=resolved_lang)}:** `{self.target_type.value.upper()}` | **{t('md_severity', lang=resolved_lang)}:** **{self.severity_level}** | **{t('md_risk_score', lang=resolved_lang)}:** `{self.risk_score:.1f}/10.0`\n",
            f"## {t('executive_summary', lang=resolved_lang)}",
            self.executive_summary,
            f"\n## {t('md_risk_assessment', lang=resolved_lang)}",
            f"- **{t('md_composite_score', lang=resolved_lang)}:** `{self.risk_score:.1f} / 10.0`",
            f"- **{t('correlated_cves', lang=resolved_lang)}:** {cves_str}",
            f"- **{t('risk_rationale', lang=resolved_lang)}:** {self.risk_rationale}\n",
            f"## {t('md_technical_evidence', lang=resolved_lang)}",
        ]

        for k, v in self.technical_evidence.items():
            md.append(f"- **{k}:** {v}")

        if self.mitre_techniques:
            md.append(f"\n## {t('md_mitre_mapping', lang=resolved_lang)}")
            md.append(
                f"| ID | {t('md_technique', lang=resolved_lang)} | {t('md_tactic', lang=resolved_lang)} | {t('md_relevance', lang=resolved_lang)} |"
            )
            md.append("| :--- | :--- | :--- | :--- |")
            for tech in self.mitre_techniques:
                md.append(
                    f"| `{tech.technique_id}` | {tech.name} | {tech.tactic} | {tech.relevance_explanation} |"
                )

        if self.mitigations:
            md.append(f"\n## {t('md_actionable_mitigations', lang=resolved_lang)}")
            for m in self.mitigations:
                md.append(f"### [{m.priority}] {m.title} ({m.category})")
                md.append(f"{m.description}\n")
                if m.actionable_steps:
                    md.append(f"**{t('md_implementation_steps', lang=resolved_lang)}:**")
                    for step in m.actionable_steps:
                        md.append(f"1. {step}")
                md.append("")

        if self.references:
            md.append(f"## {t('md_references', lang=resolved_lang)}")
            for ref in self.references:
                md.append(f"- <{ref}>")

        return "\n".join(md)
