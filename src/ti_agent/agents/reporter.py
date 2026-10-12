"""Reporter Agent: synthesizes technical evidence into validated ThreatReport (Markdown + JSON)."""

from typing import Any

from ti_agent.agents.analyst import AnalysisResult
from ti_agent.core.config import Settings, get_settings
from ti_agent.core.i18n import resolve_language
from ti_agent.core.logging import get_logger
from ti_agent.models.indicator import IndicatorType
from ti_agent.models.report import ExtractionResult, ThreatReport

logger = get_logger("ti_agent.agents.reporter")


class ReporterAgent:
    """Agent responsible for assembling and validating final Threat Intelligence reports."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _compile_technical_evidence(self, extraction: ExtractionResult) -> dict[str, Any]:
        """Aggregate evidence observed across feeds into a structured dictionary."""
        evidence: dict[str, Any] = {}

        if extraction.nvd:
            evidence["NVD Vulnerability"] = {
                "CVE ID": extraction.nvd.cve_id,
                "CVSS Base Score": extraction.nvd.score,
                "Severity": extraction.nvd.severity,
                "Vector String": extraction.nvd.cvss.vector_string
                if extraction.nvd.cvss
                else "N/A",
                "Weaknesses (CWE)": extraction.nvd.cwe_ids,
                "Affected Products": extraction.nvd.affected_cpes[:5],
            }

        if extraction.virustotal:
            evidence["VirusTotal Telemetry"] = {
                "Detection Ratio": extraction.virustotal.detection_ratio,
                "Reputation Score": extraction.virustotal.reputation,
                "Is Flagged Malicious": extraction.virustotal.is_flagged_malicious,
                "Community Tags": extraction.virustotal.community_tags,
                "Categories": extraction.virustotal.categories,
            }

        if extraction.shodan:
            evidence["Shodan Attack Surface"] = {
                "Open Ports": extraction.shodan.ports,
                "Hostnames": extraction.shodan.hostnames,
                "Organization": extraction.shodan.org or "Unknown",
                "Operating System": extraction.shodan.os or "Unknown",
                "Associated CVEs": extraction.shodan.vulns,
                "Indexed Services": [
                    f"Port {s.port}/{s.transport}: {s.product or 'unknown'}"
                    for s in extraction.shodan.services[:5]
                ],
            }

        if extraction.web_audit:
            web = extraction.web_audit
            evidence["Web Security Inspection"] = {
                "Target URL": web.url,
                "Status Code": web.status_code,
                "Security Grade": web.grade,
                "Web Risk Score": f"{web.security_score}/10.0",
                "Server Banner": web.server_banner or "Hidden/None",
                "Powered By": web.powered_by or "Hidden/None",
                "CORS Wildcard (*)": web.cors_wildcard,
                "Missing or Failed Headers": [
                    f"{c.header} ({c.severity})" for c in web.header_checks if c.status != "PASS"
                ],
                "Cookie Findings": [
                    f"{ck.name}: {', '.join(ck.findings)}"
                    for ck in web.cookie_checks
                    if ck.findings
                ],
                "OWASP Tags": web.owasp_tags,
            }

        # Document provider statuses / errors for degraded transparency
        evidence["Telemetry Provider Statuses"] = {
            s.provider: ("OK" if s.success else f"FAILED ({s.error_message})")
            for s in extraction.statuses
        }

        return evidence

    def _compile_executive_summary(
        self,
        extraction: ExtractionResult,
        analysis: AnalysisResult,
        language: str | None = None,
    ) -> str:
        """Generate concise executive summary suitable for SOC leads and management in chosen language."""
        lang = resolve_language(language, settings=self.settings)
        target = extraction.indicator.value
        target_type = extraction.indicator.type.value.upper()
        severity = analysis.severity_level
        score = analysis.risk_score

        if extraction.web_audit:
            web = extraction.web_audit
            failed_headers = [c.header for c in web.header_checks if c.status != "PASS"]
            headers_str = ", ".join(failed_headers[:4]) if failed_headers else "None"
            if lang == "es":
                return (
                    f"La inspección de seguridad de la aplicación web para la URL '{target}' concluyó con una "
                    f"puntuación de riesgo compuesta de {score:.1f}/10.0 ({severity}, Calificación: {web.grade}). "
                    f"Se identificaron cabeceras defensivas faltantes ({headers_str}) y posible "
                    f"divulgación de tecnologías. Se recomienda implementar el middleware de hardening de OWASP recomendado."
                )
            return (
                f"Web application security inspection for URL '{target}' concluded with a "
                f"composite risk score of {score:.1f}/10.0 ({severity}, Grade: {web.grade}). "
                f"Identified missing defensive security headers ({headers_str}) and potential "
                f"technology disclosures. Implementing recommended OWASP hardening middleware is strongly advised."
            )

        if extraction.indicator.type == IndicatorType.CVE and extraction.nvd:
            if lang == "es":
                return (
                    f"La evaluación autónoma de seguridad para {target_type} '{target}' concluyó con una "
                    f"puntuación de riesgo compuesta de {score:.1f}/10.0 ({severity}). "
                    f"La vulnerabilidad está calificada con CVSS {extraction.nvd.score:.1f} ({extraction.nvd.severity}) "
                    f"y permite explotación no autenticada a través de la red. "
                    f"Se recomienda parcheo inmediato y filtrado perimetral de salida."
                )
            return (
                f"Autonomous security assessment for {target_type} '{target}' concluded with a "
                f"composite risk score of {score:.1f}/10.0 ({severity}). "
                f"The vulnerability is rated CVSS {extraction.nvd.score:.1f} ({extraction.nvd.severity}) "
                f"and permits unauthenticated exploitation over network channels. "
                f"Immediate patching and perimeter egress filtering are strongly recommended."
            )

        if extraction.virustotal and extraction.virustotal.is_flagged_malicious:
            if lang == "es":
                return (
                    f"El análisis de seguridad para {target_type} '{target}' identificó asociación maliciosa activa "
                    f"con una puntuación de riesgo compuesta de {score:.1f}/10.0 ({severity}). "
                    f"Múltiples proveedores de inteligencia de amenazas ({extraction.virustotal.detection_ratio}) marcaron "
                    f"este indicador como infraestructura hostil. Se aconseja contención perimetral inmediata "
                    f"y sinkholing DNS."
                )
            return (
                f"Security analysis for {target_type} '{target}' identified active malicious association "
                f"with a composite risk score of {score:.1f}/10.0 ({severity}). "
                f"Multiple threat intelligence vendors ({extraction.virustotal.detection_ratio}) flagged "
                f"this indicator as hostile infrastructure. Immediate network boundary containment "
                f"and DNS sinkholing are advised."
            )

        if extraction.shodan and extraction.shodan.ports:
            ports_str = ", ".join(str(p) for p in extraction.shodan.ports[:6])
            if lang == "es":
                return (
                    f"La evaluación de superficie de ataque para {target_type} '{target}' concluyó con una "
                    f"puntuación de riesgo compuesta de {score:.1f}/10.0 ({severity}). "
                    f"Shodan indexó {len(extraction.shodan.ports)} puertos accesibles públicamente ({ports_str}). "
                    f"Se debe aplicar hardening de red y restricción de ingreso para prevenir reconocimiento."
                )
            return (
                f"Attack surface assessment for {target_type} '{target}' concluded with a "
                f"composite risk score of {score:.1f}/10.0 ({severity}). "
                f"Shodan indexed {len(extraction.shodan.ports)} publicly accessible ports ({ports_str}). "
                f"Network hardening and ingress restriction should be applied to prevent reconnaissance."
            )

        if lang == "es":
            return (
                f"La revisión de inteligencia de amenazas para {target_type} '{target}' finalizó con una "
                f"puntuación de riesgo compuesta de {score:.1f}/10.0 ({severity}). "
                f"No se observaron exploits activos críticos ni telemetría maliciosa severa."
            )
        return (
            f"Threat intelligence review for {target_type} '{target}' completed with a "
            f"composite risk score of {score:.1f}/10.0 ({severity}). "
            f"No critical active exploits or severe malicious telemetry were observed."
        )

    def _compile_references(
        self,
        extraction: ExtractionResult,
        analysis: AnalysisResult,
    ) -> list[str]:
        """Collect verified reference URLs from NVD, MITRE, and vendors."""
        refs: list[str] = []

        if extraction.web_audit:
            refs.extend(
                [
                    "https://owasp.org/www-project-secure-headers/",
                    "https://owasp.org/Top10/A05_2021-Security_Misconfiguration/",
                ]
            )

        if extraction.nvd and extraction.nvd.references:
            refs.extend(extraction.nvd.references)

        for t in analysis.mitre_techniques:
            url = f"https://attack.mitre.org/techniques/{t.technique_id}/"
            if url not in refs:
                refs.append(url)

        return refs[:10]

    def generate_report(
        self,
        extraction: ExtractionResult,
        analysis: AnalysisResult,
        execution_metadata: dict[str, Any] | None = None,
        language: str | None = None,
    ) -> ThreatReport:
        """Construct, validate, and return the final ThreatReport."""
        lang = resolve_language(language, settings=self.settings)
        evidence = self._compile_technical_evidence(extraction)
        executive_summary = self._compile_executive_summary(extraction, analysis, language=lang)
        references = self._compile_references(extraction, analysis)

        meta = execution_metadata or {}
        meta["degraded_mode"] = extraction.is_degraded
        meta["successful_providers"] = extraction.successful_providers
        meta["failed_providers"] = extraction.failed_providers

        # Validate strictly against ThreatReport Pydantic schema
        report = ThreatReport(
            target=extraction.indicator.value,
            target_type=extraction.indicator.type,
            executive_summary=executive_summary,
            severity_level=analysis.severity_level,  # type: ignore[arg-type]
            risk_score=analysis.risk_score,
            risk_rationale=analysis.risk_rationale,
            technical_evidence=evidence,
            correlated_cves=analysis.correlated_cves,
            mitre_techniques=analysis.mitre_techniques,
            mitigations=analysis.mitigations,
            references=references,
            language=lang,
            execution_metadata=meta,
        )

        logger.info(
            "ThreatReport %s successfully generated and validated (lang=%s).",
            report.report_id,
            lang,
        )
        return report
