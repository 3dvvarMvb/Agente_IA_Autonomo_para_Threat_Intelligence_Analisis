"""Internationalization (i18n) and localization support for threat reports."""

from __future__ import annotations

import locale
import os
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from ti_agent.core.config import Settings

SupportedLanguage = Literal["es", "en"]

# Dictionary of localized template strings and UI labels
TRANSLATIONS: dict[SupportedLanguage, dict[str, str]] = {
    "es": {
        # Dashboard & CLI labels
        "dashboard_title": "PANEL DE CONTROL DE INTELIGENCIA DE AMENAZAS",
        "target": "Objetivo",
        "type": "Tipo",
        "risk_score": "Puntuación de Riesgo",
        "severity": "Severidad",
        "correlated_cves": "CVEs Correlacionados",
        "executive_summary": "Resumen Ejecutivo",
        "risk_rationale": "Justificación de Riesgo",
        "none_observed": "Ninguno observado",
        # Table Titles
        "web_audit_table_title": "Auditoría de Línea Base de Seguridad Web OWASP",
        "web_control_column": "Control de Seguridad / Métrica",
        "web_status_column": "Resultado y Estado de Auditoría",
        "telemetry_table_title": "Evidencia Técnica y Telemetría Externa",
        "category_source_column": "Categoría / Fuente",
        "observation_column": "Observación e Inteligencia Extraída",
        "mitre_table_title": "Correlación MITRE ATT&CK",
        "tech_id_column": "ID Técnica",
        "tech_name_column": "Nombre de Técnica",
        "tactic_column": "Táctica",
        "behavior_notes_column": "Notas de Detección y Comportamiento",
        "mitigations_table_title": "Mitigaciones Accionables de Hardening y Respuesta",
        "priority_column": "Prioridad",
        "category_column": "Categoría",
        "action_title_column": "Título de Acción",
        "remediation_column": "Mecanismo de Remediación",
        # Markdown Sections
        "md_report_title": "Reporte de Inteligencia de Amenazas",
        "md_report_id": "ID de Reporte",
        "md_generated": "Generado",
        "md_indicator_type": "Tipo de Indicador",
        "md_severity": "Severidad",
        "md_risk_score": "Puntuación de Riesgo",
        "md_risk_assessment": "Evaluación de Riesgo y Justificación",
        "md_composite_score": "Puntuación de Riesgo Compuesta",
        "md_technical_evidence": "Evidencia Técnica y Observaciones",
        "md_mitre_mapping": "Mapeo MITRE ATT&CK",
        "md_technique": "Técnica",
        "md_tactic": "Táctica",
        "md_relevance": "Relevancia",
        "md_actionable_mitigations": "Mitigaciones Accionables",
        "md_implementation_steps": "Pasos de Implementación",
        "md_references": "Referencias y Avisos",
    },
    "en": {
        # Dashboard & CLI labels
        "dashboard_title": "THREAT INTELLIGENCE ANALYSIS DASHBOARD",
        "target": "Target",
        "type": "Type",
        "risk_score": "Risk Score",
        "severity": "Severity",
        "correlated_cves": "Correlated CVEs",
        "executive_summary": "Executive Summary",
        "risk_rationale": "Risk Rationale",
        "none_observed": "None observed",
        # Table Titles
        "web_audit_table_title": "OWASP Web Security Baseline Audit",
        "web_control_column": "Security Control / Metric",
        "web_status_column": "Audit Result & Status",
        "telemetry_table_title": "Technical Evidence & External Telemetry",
        "category_source_column": "Category / Source",
        "observation_column": "Observation & Extracted Intelligence",
        "mitre_table_title": "MITRE ATT&CK Correlation",
        "tech_id_column": "Technique ID",
        "tech_name_column": "Technique Name",
        "tactic_column": "Tactic",
        "behavior_notes_column": "Detection & Behavioral Notes",
        "mitigations_table_title": "Actionable Hardening & Incident Response Mitigations",
        "priority_column": "Priority",
        "category_column": "Category",
        "action_title_column": "Action Title",
        "remediation_column": "Remediation Mechanism",
        # Markdown Sections
        "md_report_title": "Threat Intelligence Report",
        "md_report_id": "Report ID",
        "md_generated": "Generated",
        "md_indicator_type": "Indicator Type",
        "md_severity": "Severity",
        "md_risk_score": "Risk Score",
        "md_risk_assessment": "Risk Assessment & Rationale",
        "md_composite_score": "Composite Risk Score",
        "md_technical_evidence": "Technical Evidence & Observations",
        "md_mitre_mapping": "MITRE ATT&CK Mapping",
        "md_technique": "Technique",
        "md_tactic": "Tactic",
        "md_relevance": "Relevance",
        "md_actionable_mitigations": "Actionable Mitigations",
        "md_implementation_steps": "Implementation Steps",
        "md_references": "References & Advisories",
    },
}


def detect_system_language() -> SupportedLanguage:
    """Detect the host operating system display language.

    Inspects environment locale variables (LC_ALL, LC_MESSAGES, LANG)
    and Python standard library locale. If Spanish is detected,
    returns 'es', otherwise defaults to 'en'.
    """
    candidates: list[str] = []
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            candidates.append(val)

    try:
        loc = locale.getlocale()[0]
        if loc:
            candidates.append(loc)
    except Exception:
        pass

    try:
        # Fallback for systems where getlocale is unset
        defloc = locale.getdefaultlocale()[0]
        if defloc:
            candidates.append(defloc)
    except Exception:
        pass

    for candidate in candidates:
        cand_lower = candidate.lower()
        if cand_lower.startswith(("es", "spanish")):
            return "es"

    return "en"


def resolve_language(
    lang: str | None = None,
    settings: Settings | None = None,
) -> SupportedLanguage:
    """Resolve report language from parameter, configuration settings, or OS display language.

    Priority order:
    1. Explicit parameter `lang` (if 'es' or 'en')
    2. Settings configured `report_language` (if 'es' or 'en')
    3. Automatic host OS display language detection (`detect_system_language()`)
    """
    if lang:
        normalized = lang.strip().lower()
        if normalized in ("es", "spanish", "esp"):
            return "es"
        if normalized in ("en", "english", "eng"):
            return "en"

    if settings is not None:
        cfg_lang = getattr(settings, "report_language", "auto")
        if cfg_lang in ("es", "en"):
            return cast(SupportedLanguage, cfg_lang)
    else:
        # Import lazily to avoid circular dependencies
        try:
            from ti_agent.core.config import get_settings

            cfg = get_settings()
            if cfg.report_language in ("es", "en"):
                return cfg.report_language
        except Exception:
            pass

    return detect_system_language()


def t(key: str, lang: SupportedLanguage = "es", **kwargs: Any) -> str:
    """Retrieve localized string for given key and language with optional formatting."""
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    text = lang_dict.get(key, TRANSLATIONS["en"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text
