"""Integration tests for Threat Intelligence CLI."""

import json
from pathlib import Path

from typer.testing import CliRunner

from ti_agent.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    """Verify 'version' command outputs version number."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_cli_help() -> None:
    """Verify root help displays primary subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.stdout
    assert "rag" in result.stdout
    assert "cache" in result.stdout


def test_cli_analyze_help() -> None:
    """Verify 'analyze --help' displays parameter documentation."""
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--offline" in result.stdout
    assert "--format" in result.stdout
    assert "--output" in result.stdout


def test_cli_analyze_cve_offline() -> None:
    """Verify offline CVE analysis generates full report."""
    result = runner.invoke(app, ["analyze", "CVE-2021-44228", "--offline"])
    assert result.exit_code == 0
    assert "CVE-2021-44228" in result.stdout
    assert "10.0" in result.stdout
    assert "CRITICAL" in result.stdout
    assert "T1190" in result.stdout


def test_cli_analyze_ip_offline() -> None:
    """Verify offline IP analysis generates full report."""
    result = runner.invoke(app, ["analyze", "8.8.8.8", "--offline"])
    assert result.exit_code == 0
    assert "8.8.8.8" in result.stdout
    assert "VirusTotal" in result.stdout or "Shodan" in result.stdout


def test_cli_analyze_json_file_export(tmp_path: Path) -> None:
    """Verify JSON file export produces valid ThreatReport JSON payload."""
    out_file = tmp_path / "test_report.json"
    result = runner.invoke(
        app,
        [
            "analyze",
            "CVE-2021-44228",
            "--offline",
            "--format",
            "json",
            "-o",
            str(out_file),
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["target"] == "CVE-2021-44228"
    assert data["severity_level"] == "CRITICAL"
    assert data["risk_score"] == 10.0
    assert len(data["mitre_techniques"]) >= 1


def test_cli_analyze_both_formats_export(tmp_path: Path) -> None:
    """Verify '--format both' generates both markdown and json files."""
    base_file = tmp_path / "multi_report"
    result = runner.invoke(
        app,
        [
            "analyze",
            "8.8.8.8",
            "--offline",
            "--format",
            "both",
            "-o",
            str(base_file),
        ],
    )
    assert result.exit_code == 0
    md_file = tmp_path / "multi_report.md"
    json_file = tmp_path / "multi_report.json"
    assert md_file.exists()
    assert json_file.exists()
    md_content = md_file.read_text(encoding="utf-8")
    assert (
        "Threat Intelligence Report" in md_content
        or "Reporte de Inteligencia de Amenazas" in md_content
    )


def test_cli_analyze_quiet_json_stdout() -> None:
    """Verify '--quiet --format json' outputs raw parsable JSON to stdout."""
    result = runner.invoke(
        app,
        ["analyze", "CVE-2021-44228", "--offline", "--quiet", "--format", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout.strip())
    assert data["target"] == "CVE-2021-44228"
    assert "report_id" in data


def test_cli_analyze_invalid_indicator_exits_with_error() -> None:
    """Verify invalid indicator string raises validation error with exit code 1."""
    result = runner.invoke(app, ["analyze", "invalid_target_string_12345!"])
    assert result.exit_code == 1
    assert "Validation Error" in result.output or "Error" in result.output


def test_cli_cache_clear() -> None:
    """Verify cache clear command executes successfully."""
    result = runner.invoke(app, ["cache", "clear"])
    assert result.exit_code == 0
    assert "Cleared" in result.stdout


def test_cli_rag_ingest_and_eval(tmp_path: Path) -> None:
    """Verify RAG ingest and eval commands against an isolated ChromaDB directory."""
    persist_dir = tmp_path / "test_chroma_cli"

    # Ingest
    ingest_res = runner.invoke(
        app,
        ["rag", "ingest", "--persist-dir", str(persist_dir)],
    )
    assert ingest_res.exit_code == 0
    assert "INDEXED SUCCESSFULLY" in ingest_res.stdout

    # Eval
    eval_res = runner.invoke(
        app,
        ["rag", "eval", "--persist-dir", str(persist_dir)],
    )
    assert eval_res.exit_code == 0
    assert "Hit Rate" in eval_res.stdout
    assert "100.0%" in eval_res.stdout


def test_cli_analyze_url_localhost_offline() -> None:
    """Verify 'ti-agent analyze http://localhost:8080/dashboard --offline' audits web security."""
    result = runner.invoke(app, ["analyze", "http://localhost:8080/dashboard", "--offline"])
    assert result.exit_code == 0
    assert "http://localhost:8080/dashboard" in result.stdout
    assert (
        "OWASP Web Security Baseline Audit" in result.stdout
        or "Seguridad Web OWASP" in result.stdout
    )
    assert "Content-Security-Policy" in result.stdout
    assert "X-Frame-Options" in result.stdout
    assert "uvicorn" in result.stdout or "Express" in result.stdout


def test_cli_audit_web_offline() -> None:
    """Verify 'ti-agent audit-web http://localhost:8080/dashboard --offline' executes audit pipeline."""
    result = runner.invoke(app, ["audit-web", "http://localhost:8080/dashboard", "--offline"])
    assert result.exit_code == 0
    assert "http://localhost:8080/dashboard" in result.stdout
    assert (
        "OWASP Web Security Baseline Audit" in result.stdout
        or "Seguridad Web OWASP" in result.stdout
    )


def test_cli_audit_web_json_export(tmp_path: Path) -> None:
    """Verify 'ti-agent audit-web' exports JSON with web_audit findings."""
    out_file = tmp_path / "web_audit_report.json"
    result = runner.invoke(
        app,
        [
            "audit-web",
            "http://localhost:8080/dashboard",
            "--offline",
            "--format",
            "json",
            "-o",
            str(out_file),
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["target"] == "http://localhost:8080/dashboard"
    assert "technical_evidence" in data
    assert "Web Security Inspection" in data["technical_evidence"]
    web_ev = data["technical_evidence"]["Web Security Inspection"]
    assert web_ev["Status Code"] == 200
    assert web_ev["Security Grade"] in ("D", "F")


def test_cli_analyze_explicit_lang_en() -> None:
    """Verify '--lang en' outputs English dashboard and report."""
    result = runner.invoke(app, ["analyze", "CVE-2021-44228", "--offline", "--lang", "en"])
    assert result.exit_code == 0
    assert "THREAT INTELLIGENCE ANALYSIS DASHBOARD" in result.stdout
    assert "Executive Summary:" in result.stdout
    assert "Risk Score:" in result.stdout


def test_cli_analyze_explicit_lang_es() -> None:
    """Verify '--lang es' outputs Spanish dashboard and report."""
    result = runner.invoke(app, ["analyze", "CVE-2021-44228", "--offline", "--lang", "es"])
    assert result.exit_code == 0
    assert "PANEL DE CONTROL DE INTELIGENCIA DE AMENAZAS" in result.stdout
    assert "Resumen Ejecutivo:" in result.stdout
    assert "Puntuación de Riesgo:" in result.stdout
