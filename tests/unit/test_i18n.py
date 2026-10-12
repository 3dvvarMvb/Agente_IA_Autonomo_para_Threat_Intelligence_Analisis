"""Unit tests for internationalization, language resolution, and localized reports."""

import pytest

from ti_agent.core.config import Settings
from ti_agent.core.i18n import detect_system_language, resolve_language, t
from ti_agent.models.indicator import IndicatorType
from ti_agent.models.report import ThreatReport


class TestI18nResolution:
    """Test OS detection and language resolution rules."""

    def test_detect_spanish_from_lang_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LC_ALL", "")
        monkeypatch.setenv("LC_MESSAGES", "")
        monkeypatch.setenv("LANG", "es_MX.UTF-8")
        assert detect_system_language() == "es"

    def test_detect_english_from_lang_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LC_MESSAGES", raising=False)
        monkeypatch.setenv("LANG", "en_US.UTF-8")
        monkeypatch.setattr("locale.getlocale", lambda: ("en_US", "UTF-8"))
        assert detect_system_language() == "en"

    def test_resolve_language_explicit_cli(self) -> None:
        assert resolve_language("es") == "es"
        assert resolve_language("en") == "en"
        assert resolve_language("SPANISH") == "es"
        assert resolve_language("ENGLISH") == "en"

    def test_resolve_language_settings_override(self) -> None:
        cfg_es = Settings(report_language="es")
        assert resolve_language(None, settings=cfg_es) == "es"

        cfg_en = Settings(report_language="en")
        assert resolve_language(None, settings=cfg_en) == "en"

    def test_resolve_language_cli_takes_precedence_over_settings(self) -> None:
        cfg_es = Settings(report_language="es")
        assert resolve_language("en", settings=cfg_es) == "en"

    def test_t_function_translations(self) -> None:
        assert t("dashboard_title", lang="es") == "PANEL DE CONTROL DE INTELIGENCIA DE AMENAZAS"
        assert t("dashboard_title", lang="en") == "THREAT INTELLIGENCE ANALYSIS DASHBOARD"
        assert t("target", lang="es") == "Objetivo"
        assert t("target", lang="en") == "Target"


class TestLocalizedReportGeneration:
    """Test rendering ThreatReport in Spanish and English."""

    @pytest.fixture
    def sample_report(self) -> ThreatReport:
        return ThreatReport(
            target="http://localhost:8080/dashboard",
            target_type=IndicatorType.URL,
            executive_summary="Resumen ejecutivo de prueba",
            severity_level="HIGH",
            risk_score=7.5,
            risk_rationale="Justificación de riesgo calculada",
            technical_evidence={"Prueba": "Valor"},
            correlated_cves=[],
            mitre_techniques=[],
            mitigations=[],
            references=[],
            language="es",
        )

    def test_to_markdown_spanish(self, sample_report: ThreatReport) -> None:
        md = sample_report.to_markdown(lang="es")
        assert "# Reporte de Inteligencia de Amenazas: http://localhost:8080/dashboard" in md
        assert "**ID de Reporte:**" in md
        assert "**Tipo de Indicador:** `URL`" in md
        assert "**Puntuación de Riesgo:** `7.5/10.0`" in md
        assert "## Resumen Ejecutivo" in md
        assert "## Evaluación de Riesgo y Justificación" in md
        assert "## Evidencia Técnica y Observaciones" in md

    def test_to_markdown_english(self, sample_report: ThreatReport) -> None:
        md = sample_report.to_markdown(lang="en")
        assert "# Threat Intelligence Report: http://localhost:8080/dashboard" in md
        assert "**Report ID:**" in md
        assert "**Indicator Type:** `URL`" in md
        assert "**Risk Score:** `7.5/10.0`" in md
        assert "## Executive Summary" in md
        assert "## Risk Assessment & Rationale" in md
        assert "## Technical Evidence & Observations" in md
