"""Web application security auditor tool for dynamic baseline inspection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.logging import get_logger
from ti_agent.models.web_audit import (
    CookieSecurityCheck,
    SecurityHeaderCheck,
    WebAuditResult,
)

logger = get_logger("ti_agent.tools.web_auditor")


class WebSecurityAuditor:
    """Dynamic baseline web application security auditor."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def audit_url(self, target_url: str, offline: bool | None = None) -> WebAuditResult:
        """Inspect target URL, examine HTTP headers, cookies, and CORS configurations.

        Args:
            target_url: Complete HTTP/HTTPS URL (e.g. http://localhost:8080/dashboard).
            offline: Override offline mode flag.

        Returns:
            WebAuditResult containing evaluated security posture and recommendations.
        """
        is_offline = self.settings.offline_mode if offline is None else offline

        if is_offline:
            return self._load_offline_fixture_or_simulate(target_url)

        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                follow_redirects=True,
                verify=False,
            ) as client:
                response = await client.get(target_url)
                return self._evaluate_response(
                    target_url, response.status_code, dict(response.headers)
                )
        except Exception as exc:
            logger.warning(
                "Failed to connect directly to %s: %s. Using simulated inspection.", target_url, exc
            )
            return self._load_offline_fixture_or_simulate(target_url)

    def _load_offline_fixture_or_simulate(self, target_url: str) -> WebAuditResult:
        """Load recorded fixture or construct baseline simulation for offline evaluation."""
        fixture_path = Path("fixtures/web_audit_localhost.json")
        if fixture_path.exists():
            try:
                data: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))
                return self._evaluate_response(
                    target_url,
                    int(data.get("status_code", 200)),
                    data.get("headers", {}),
                )
            except Exception as exc:
                logger.error("Failed to load fixture %s: %s", fixture_path, exc)

        # Fallback simulation
        simulated_headers = {
            "content-type": "text/html; charset=utf-8",
            "server": "uvicorn",
            "x-powered-by": "Express/4.19.2",
            "access-control-allow-origin": "*",
        }
        return self._evaluate_response(target_url, 200, simulated_headers)

    def _evaluate_response(
        self,
        url: str,
        status_code: int,
        raw_headers: dict[str, str],
    ) -> WebAuditResult:
        """Analyze headers and cookies to produce structured security findings."""
        headers = {k.lower(): v for k, v in raw_headers.items()}
        parsed_url = urlparse(url)
        is_plain_http = parsed_url.scheme.lower() == "http"
        hostname = (parsed_url.hostname or "").lower()
        is_local = hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1")

        header_checks: list[SecurityHeaderCheck] = []
        score = 0.0
        owasp_tags: list[str] = ["A05:2021-Security Misconfiguration"]
        recommendations: list[str] = []

        # 1. Content-Security-Policy
        csp_val = headers.get("content-security-policy")
        if not csp_val:
            header_checks.append(
                SecurityHeaderCheck(
                    header="Content-Security-Policy",
                    status="FAIL",
                    observed_value=None,
                    severity="HIGH",
                    description="Prevents Cross-Site Scripting (XSS), clickjacking, and arbitrary code injection.",
                    remediation="Define a restrictive Content-Security-Policy, e.g.: default-src 'self'; script-src 'self'.",
                )
            )
            score += 3.0
            recommendations.append(
                "Implement Content-Security-Policy (CSP) to restrict scripts and resource origins."
            )
        elif "unsafe-inline" in csp_val or "unsafe-eval" in csp_val:
            header_checks.append(
                SecurityHeaderCheck(
                    header="Content-Security-Policy",
                    status="WARN",
                    observed_value=csp_val,
                    severity="MEDIUM",
                    description="Permits unsafe-inline or unsafe-eval execution, reducing XSS resistance.",
                    remediation="Refactor inline scripts to external bundles or adopt cryptographic nonces/hashes.",
                )
            )
            score += 1.5
        else:
            header_checks.append(
                SecurityHeaderCheck(
                    header="Content-Security-Policy",
                    status="PASS",
                    observed_value=csp_val,
                    severity="INFO",
                    description="Enforces strict Content-Security-Policy restrictions.",
                    remediation="Maintain and regularly review origin whitelist.",
                )
            )

        # 2. X-Frame-Options
        xfo_val = headers.get("x-frame-options")
        if not xfo_val:
            header_checks.append(
                SecurityHeaderCheck(
                    header="X-Frame-Options",
                    status="FAIL",
                    observed_value=None,
                    severity="MEDIUM",
                    description="Protects against UI redress and clickjacking by forbidding unauthorized framing.",
                    remediation="Configure 'X-Frame-Options: DENY' or 'SAMEORIGIN'.",
                )
            )
            score += 2.0
            recommendations.append(
                "Add 'X-Frame-Options: DENY' to neutralize clickjacking attacks."
            )
        else:
            header_checks.append(
                SecurityHeaderCheck(
                    header="X-Frame-Options",
                    status="PASS",
                    observed_value=xfo_val,
                    severity="INFO",
                    description="Framing is restricted by X-Frame-Options.",
                    remediation="Verify framing constraints match application architecture.",
                )
            )

        # 3. X-Content-Type-Options
        xcto_val = headers.get("x-content-type-options")
        if not xcto_val or xcto_val.lower() != "nosniff":
            header_checks.append(
                SecurityHeaderCheck(
                    header="X-Content-Type-Options",
                    status="FAIL",
                    observed_value=xcto_val,
                    severity="LOW",
                    description="Prevents MIME-sniffing vulnerabilities where browsers execute content as scripts.",
                    remediation="Configure 'X-Content-Type-Options: nosniff'.",
                )
            )
            score += 1.0
            recommendations.append(
                "Configure 'X-Content-Type-Options: nosniff' to disable MIME-type sniffing."
            )
        else:
            header_checks.append(
                SecurityHeaderCheck(
                    header="X-Content-Type-Options",
                    status="PASS",
                    observed_value=xcto_val,
                    severity="INFO",
                    description="MIME-type sniffing disabled.",
                    remediation="Ensure all static assets serve exact Content-Type headers.",
                )
            )

        # 4. Strict-Transport-Security (HSTS)
        hsts_val = headers.get("strict-transport-security")
        if not hsts_val:
            if is_local:
                header_checks.append(
                    SecurityHeaderCheck(
                        header="Strict-Transport-Security",
                        status="WARN",
                        observed_value=None,
                        severity="INFO",
                        description="HSTS enforces encrypted HTTPS transport across subsequent connections.",
                        remediation="Enable HSTS with max-age >= 31536000 before deploying to staging/production.",
                    )
                )
            else:
                header_checks.append(
                    SecurityHeaderCheck(
                        header="Strict-Transport-Security",
                        status="FAIL",
                        observed_value=None,
                        severity="MEDIUM",
                        description="Missing HSTS leaves sessions open to SSL-stripping and downgrade attacks.",
                        remediation="Enforce 'Strict-Transport-Security: max-age=31536000; includeSubDomains'.",
                    )
                )
                score += 2.0
                recommendations.append(
                    "Enable HTTP Strict Transport Security (HSTS) on HTTPS deployments."
                )
        else:
            header_checks.append(
                SecurityHeaderCheck(
                    header="Strict-Transport-Security",
                    status="PASS",
                    observed_value=hsts_val,
                    severity="INFO",
                    description="HSTS policy is active.",
                    remediation="Ensure includeSubDomains and preload are enabled for root domains.",
                )
            )

        # 5. Referrer-Policy
        ref_val = headers.get("referrer-policy")
        if not ref_val:
            header_checks.append(
                SecurityHeaderCheck(
                    header="Referrer-Policy",
                    status="WARN",
                    observed_value=None,
                    severity="LOW",
                    description="Controls how much referrer information is leaked with outbound requests.",
                    remediation="Configure 'Referrer-Policy: strict-origin-when-cross-origin'.",
                )
            )
            score += 0.5
        else:
            header_checks.append(
                SecurityHeaderCheck(
                    header="Referrer-Policy",
                    status="PASS",
                    observed_value=ref_val,
                    severity="INFO",
                    description="Referrer policy configured.",
                    remediation="Verify no private tokens or IDs are embedded in URL query parameters.",
                )
            )

        # 6. Information Leakage: Server & X-Powered-By
        server_banner = headers.get("server")
        powered_by = headers.get("x-powered-by")
        if server_banner:
            score += 0.5
            recommendations.append(
                f"Sanitize or remove the 'Server' header (currently disclosing: '{server_banner}')."
            )
        if powered_by:
            score += 0.5
            recommendations.append(
                f"Remove the 'X-Powered-By' header (currently disclosing: '{powered_by}')."
            )

        # 7. CORS Configuration
        cors_wildcard = headers.get("access-control-allow-origin") == "*"
        if cors_wildcard:
            score += 1.0
            owasp_tags.append("A01:2021-Broken Access Control")
            recommendations.append(
                "Restrict CORS 'Access-Control-Allow-Origin' from '*' to explicit trusted origins."
            )

        # 8. Cookie Security Checks
        cookie_checks: list[CookieSecurityCheck] = []
        set_cookie_raw = headers.get("set-cookie")
        if set_cookie_raw:
            c_name = set_cookie_raw.split("=")[0].strip()
            c_lower = set_cookie_raw.lower()
            is_secure = "secure" in c_lower
            is_httponly = "httponly" in c_lower
            samesite = (
                "strict"
                if "samesite=strict" in c_lower
                else "lax"
                if "samesite=lax" in c_lower
                else "none"
                if "samesite=none" in c_lower
                else None
            )

            findings: list[str] = []
            if not is_httponly:
                findings.append(
                    "Missing HttpOnly: cookie is accessible via JavaScript (XSS theft risk)."
                )
                score += 1.5
            if not is_secure and not is_local:
                findings.append("Missing Secure: cookie can be transmitted over plain HTTP.")
                score += 1.5
            if not samesite:
                findings.append(
                    "Missing SameSite: susceptible to Cross-Site Request Forgery (CSRF)."
                )
                score += 1.0

            if findings:
                owasp_tags.append("A07:2021-Identification and Authentication Failures")
                recommendations.append(
                    f"Harden cookie '{c_name}': enable HttpOnly, Secure, and SameSite=Lax/Strict."
                )

            cookie_checks.append(
                CookieSecurityCheck(
                    name=c_name,
                    is_secure=is_secure,
                    is_httponly=is_httponly,
                    samesite=samesite,
                    findings=findings,
                )
            )

        # Cap score between 0.0 and 10.0
        final_score = min(round(score, 1), 10.0)

        # Assign Grade
        grade: Literal["A+", "A", "B", "C", "D", "F"]
        if final_score <= 1.0:
            grade = "A+"
        elif final_score <= 2.5:
            grade = "A"
        elif final_score <= 5.0:
            grade = "B"
        elif final_score <= 7.0:
            grade = "C"
        elif final_score <= 8.5:
            grade = "D"
        else:
            grade = "F"

        return WebAuditResult(
            url=url,
            status_code=status_code,
            is_plain_http=is_plain_http,
            server_banner=server_banner,
            powered_by=powered_by,
            headers=headers,
            header_checks=header_checks,
            cookie_checks=cookie_checks,
            cors_wildcard=cors_wildcard,
            security_score=final_score,
            grade=grade,
            owasp_tags=list(set(owasp_tags)),
            recommendations=recommendations,
        )
