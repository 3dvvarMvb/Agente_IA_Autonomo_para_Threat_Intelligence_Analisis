"""Unit tests for WebSecurityAuditor tool and WebAuditResult models."""

import pytest
from pytest_httpx import HTTPXMock

from ti_agent.core.config import Settings
from ti_agent.models.web_audit import CookieSecurityCheck, SecurityHeaderCheck, WebAuditResult
from ti_agent.tools.web_auditor import WebSecurityAuditor


class TestWebAuditModels:
    """Test web audit domain models and validations."""

    def test_security_header_check_model(self) -> None:
        check = SecurityHeaderCheck(
            header="Content-Security-Policy",
            status="FAIL",
            observed_value=None,
            severity="HIGH",
            description="Prevents XSS attacks by restricting sources of executable content.",
            remediation="Define a strong Content-Security-Policy header.",
        )
        assert check.header == "Content-Security-Policy"
        assert check.status == "FAIL"
        assert check.observed_value is None
        assert check.severity == "HIGH"
        assert "XSS" in check.description

    def test_cookie_security_check_model(self) -> None:
        cookie = CookieSecurityCheck(
            name="session_id",
            is_secure=False,
            is_httponly=False,
            samesite=None,
            findings=["Missing HttpOnly flag", "Missing Secure flag"],
        )
        assert cookie.name == "session_id"
        assert cookie.is_secure is False
        assert cookie.is_httponly is False
        assert len(cookie.findings) == 2

    def test_web_audit_result_properties(self) -> None:
        result = WebAuditResult(
            url="http://localhost:8080/dashboard",
            status_code=200,
            is_plain_http=True,
            server_banner="uvicorn",
            powered_by="Express 4.19.2",
            headers={"server": "uvicorn", "x-powered-by": "Express 4.19.2"},
            header_checks=[
                SecurityHeaderCheck(
                    header="Content-Security-Policy",
                    status="FAIL",
                    observed_value=None,
                    severity="HIGH",
                    description="CSP protection",
                    remediation="Add CSP",
                ),
                SecurityHeaderCheck(
                    header="X-Frame-Options",
                    status="PASS",
                    observed_value="DENY",
                    severity="MEDIUM",
                    description="Clickjacking protection",
                    remediation="Keep DENY",
                ),
            ],
            cookie_checks=[],
            cors_wildcard=True,
            security_score=7.5,
            grade="D",
            owasp_tags=["A05:2021-Security Misconfiguration"],
            recommendations=["Add CSP header", "Restrict CORS wildcard"],
        )
        assert result.url == "http://localhost:8080/dashboard"
        assert result.grade == "D"
        assert result.security_score == 7.5
        assert result.cors_wildcard is True
        assert result.server_banner == "uvicorn"
        assert result.powered_by == "Express 4.19.2"
        assert result.passed_checks_count == 1
        assert result.total_checks_count == 2


class TestWebSecurityAuditor:
    """Test WebSecurityAuditor dynamic inspection and fixture fallbacks."""

    @pytest.mark.asyncio
    async def test_audit_offline_fixture_localhost(self) -> None:
        """In offline mode, auditor loads fixture/web_audit_localhost.json."""
        settings = Settings(offline_mode=True)
        auditor = WebSecurityAuditor(settings=settings)

        result = await auditor.audit_url("http://localhost:8080/dashboard")

        assert result.url == "http://localhost:8080/dashboard"
        assert result.status_code == 200
        assert result.grade in ("D", "F")
        assert result.security_score >= 5.0

        # Disclosed technologies check
        assert result.server_banner == "uvicorn"
        assert result.powered_by == "Express/4.19.2"

        # Missing headers check
        failed_headers = [h.header for h in result.header_checks if h.status == "FAIL"]
        assert "Content-Security-Policy" in failed_headers
        assert "X-Frame-Options" in failed_headers
        assert "X-Content-Type-Options" in failed_headers

        # Insecure cookie check
        assert len(result.cookie_checks) > 0
        insecure_cookies = [c for c in result.cookie_checks if not c.is_httponly]
        assert len(insecure_cookies) > 0

        # CORS wildcard check
        assert result.cors_wildcard is True

    @pytest.mark.asyncio
    async def test_audit_live_mocked_hardened_site(self, httpx_mock: HTTPXMock) -> None:
        """Audit a securely configured site with all recommended security headers."""
        url = "https://secure-app.example.com/"
        headers = {
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=()",
            "Set-Cookie": "session_id=secure123; HttpOnly; Secure; SameSite=Strict; Path=/",
        }
        httpx_mock.add_response(
            url=url,
            status_code=200,
            headers=headers,
        )

        settings = Settings(offline_mode=False)
        auditor = WebSecurityAuditor(settings=settings)
        result = await auditor.audit_url(url)

        assert result.url == url
        assert result.status_code == 200
        assert result.grade in ("A+", "A")
        assert result.security_score <= 2.0
        assert result.passed_checks_count == result.total_checks_count
        assert len(result.cookie_checks) == 1
        assert result.cookie_checks[0].is_httponly is True
        assert result.cookie_checks[0].is_secure is True
        assert (result.cookie_checks[0].samesite or "").lower() == "strict"

    @pytest.mark.asyncio
    async def test_audit_live_mocked_insecure_site(self, httpx_mock: HTTPXMock) -> None:
        """Audit an insecure site with tech disclosures and wildcards."""
        url = "http://insecure-app.local/"
        headers = {
            "Server": "Apache/2.4.41 (Ubuntu)",
            "X-Powered-By": "PHP/7.4.3",
            "Access-Control-Allow-Origin": "*",
            "Set-Cookie": "auth_token=abc; Path=/",
        }
        httpx_mock.add_response(
            url=url,
            status_code=200,
            headers=headers,
        )

        settings = Settings(offline_mode=False)
        auditor = WebSecurityAuditor(settings=settings)
        result = await auditor.audit_url(url)

        assert result.grade == "F"
        assert result.security_score >= 7.0
        assert result.server_banner == "Apache/2.4.41 (Ubuntu)"
        assert result.powered_by == "PHP/7.4.3"
        assert result.cors_wildcard is True
        assert any("Content-Security-Policy" in r for r in result.recommendations)
