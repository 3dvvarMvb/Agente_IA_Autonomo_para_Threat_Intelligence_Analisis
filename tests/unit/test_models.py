"""Unit tests for domain models, validation, and parsing logic."""

import pytest

from ti_agent.core.exceptions import IndicatorValidationError
from ti_agent.models.indicator import IndicatorType, ParsedIndicator
from ti_agent.models.nvd import NvdCveData
from ti_agent.models.report import (
    ExtractionResult,
    Mitigation,
    MitreTechnique,
    ProviderStatus,
    ThreatReport,
)
from ti_agent.models.shodan import ShodanData
from ti_agent.models.virustotal import VirusTotalData


class TestIndicatorParsing:
    """Test parsing and classification of indicators."""

    def test_parse_ipv4(self) -> None:
        indicator = ParsedIndicator.parse("192.168.1.1")
        assert indicator.type == IndicatorType.IP
        assert indicator.value == "192.168.1.1"

    def test_parse_ipv6(self) -> None:
        indicator = ParsedIndicator.parse("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        assert indicator.type == IndicatorType.IP
        assert indicator.value == "2001:db8:85a3::8a2e:370:7334"

    def test_parse_domain(self) -> None:
        indicator = ParsedIndicator.parse("https://evil-site.co.uk/path?query=1")
        assert indicator.type == IndicatorType.DOMAIN
        assert indicator.value == "evil-site.co.uk"

    def test_parse_plain_domain(self) -> None:
        indicator = ParsedIndicator.parse("api.github.com")
        assert indicator.type == IndicatorType.DOMAIN
        assert indicator.value == "api.github.com"

    def test_parse_md5(self) -> None:
        raw = "44D88612FEA8A8F36DE82E1278ABB02F"
        indicator = ParsedIndicator.parse(raw)
        assert indicator.type == IndicatorType.HASH_MD5
        assert indicator.value == raw.lower()
        assert indicator.type.is_hash is True

    def test_parse_sha1(self) -> None:
        raw = "2fd4e1c67a2d28fced849ee1bb76e7391b93eb12"
        indicator = ParsedIndicator.parse(raw)
        assert indicator.type == IndicatorType.HASH_SHA1
        assert indicator.value == raw.lower()
        assert indicator.type.is_hash is True

    def test_parse_sha256(self) -> None:
        raw = "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855"
        indicator = ParsedIndicator.parse(raw)
        assert indicator.type == IndicatorType.HASH_SHA256
        assert indicator.value == raw.lower()

    def test_parse_cve(self) -> None:
        indicator = ParsedIndicator.parse("cve-2021-44228")
        assert indicator.type == IndicatorType.CVE
        assert indicator.value == "CVE-2021-44228"
        assert indicator.type.is_hash is False

    def test_parse_empty_raises(self) -> None:
        with pytest.raises(IndicatorValidationError):
            ParsedIndicator.parse("   ")

    def test_parse_invalid_indicator_raises(self) -> None:
        with pytest.raises(IndicatorValidationError) as exc:
            ParsedIndicator.parse("random_garbage_string_without_tld")
        assert "Unable to recognize indicator format" in str(exc.value)


class TestVirusTotalModel:
    """Test VirusTotalData model extraction and computation."""

    def test_from_api_response(self, vt_ip_payload: dict) -> None:
        data = VirusTotalData.from_api_response("8.8.8.8", "ip", vt_ip_payload)
        assert data.target == "8.8.8.8"
        assert data.reputation == 85
        assert data.stats.harmless == 78
        assert data.stats.malicious == 0
        assert data.stats.positive_engines == 0
        assert data.is_flagged_malicious is False
        assert data.detection_ratio == "0/90"
        assert "google" in data.community_tags

    def test_malicious_domain(self, vt_domain_payload: dict) -> None:
        data = VirusTotalData.from_api_response(
            "c2-malicious-traffic.net", "domain", vt_domain_payload
        )
        assert data.is_flagged_malicious is True
        assert data.stats.malicious == 42
        assert data.detection_ratio == "48/71"


class TestShodanModel:
    """Test ShodanData model parsing."""

    def test_from_api_response(self, shodan_ip_payload: dict) -> None:
        data = ShodanData.from_api_response("8.8.8.8", shodan_ip_payload)
        assert data.ip == "8.8.8.8"
        assert 53 in data.ports
        assert 443 in data.ports
        assert data.org == "Google LLC"
        assert "CVE-2019-0708" in data.vulns
        assert data.has_known_vulnerabilities is True
        assert len(data.services) == 2
        assert data.services[0].port == 53
        assert "Recursion: enabled" in (data.services[0].banner_snippet or "")


class TestNvdModel:
    """Test NvdCveData model parsing."""

    def test_from_api_response(self, nvd_cve_payload: dict) -> None:
        data = NvdCveData.from_api_response(nvd_cve_payload)
        assert data.cve_id == "CVE-2021-44228"
        assert "Log4j2" in data.description
        assert data.severity == "CRITICAL"
        assert data.score == 10.0
        assert data.cvss is not None
        assert data.cvss.exploitability_score == 3.9
        assert "CWE-502" in data.cwe_ids
        assert len(data.affected_cpes) > 0
        assert len(data.references) > 0


class TestThreatReportModel:
    """Test ThreatReport and Markdown rendering."""

    def test_report_generation_and_markdown(self) -> None:
        report = ThreatReport(
            target="CVE-2021-44228",
            target_type=IndicatorType.CVE,
            executive_summary="Critical remote code execution vulnerability in Log4j.",
            severity_level="CRITICAL",
            risk_score=10.0,
            risk_rationale="Unauthenticated network RCE with public exploit code.",
            technical_evidence={"CVSS": 10.0, "Vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"},
            correlated_cves=["CVE-2021-44228"],
            mitre_techniques=[
                MitreTechnique(
                    technique_id="T1190",
                    name="Exploit Public-Facing Application",
                    tactic="Initial Access",
                    description="Adversaries may attempt to exploit a vulnerability in a public application.",
                    relevance_explanation="Log4j triggers JNDI lookup via attacker controlled headers.",
                )
            ],
            mitigations=[
                Mitigation(
                    title="Upgrade Log4j to >= 2.17.1",
                    description="Patches the vulnerable JNDI lookup code.",
                    priority="CRITICAL",
                    category="Patching",
                    actionable_steps=["Update pom.xml dependencies", "Redeploy JVM containers"],
                )
            ],
            references=["https://logging.apache.org/log4j/2.x/security.html"],
        )

        md = report.to_markdown()
        assert "# Threat Intelligence Report: CVE-2021-44228" in md
        assert "CRITICAL" in md
        assert "T1190" in md
        assert "Upgrade Log4j" in md
        assert report.report_id.startswith("TR-")

    def test_extraction_result_helpers(self) -> None:
        indicator = ParsedIndicator.parse("1.1.1.1")
        res = ExtractionResult(
            indicator=indicator,
            statuses=[
                ProviderStatus(provider="virustotal", success=True, elapsed_ms=120.0),
                ProviderStatus(provider="shodan", success=False, error_message="Timeout", elapsed_ms=5000.0),
            ],
        )
        assert res.is_degraded is True
        assert res.successful_providers == ["virustotal"]
        assert res.failed_providers == ["shodan"]
