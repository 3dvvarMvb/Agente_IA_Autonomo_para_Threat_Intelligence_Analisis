"""Web application security and DAST auditing domain models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SecurityHeaderCheck(BaseModel):
    """Result of evaluating a specific security header."""

    model_config = ConfigDict(frozen=True)

    header: str = Field(description="Name of the security header evaluated")
    status: Literal["PASS", "WARN", "FAIL"] = Field(
        description="Check status: PASS (secure), WARN (improper value), FAIL (missing)"
    )
    observed_value: str | None = Field(
        default=None, description="Actual header value returned by the server"
    )
    severity: Literal["HIGH", "MEDIUM", "LOW", "INFO"] = Field(
        description="Risk severity if missing or misconfigured"
    )
    description: str = Field(description="Purpose and protection provided by the header")
    remediation: str = Field(description="Recommended value and implementation guideline")


class CookieSecurityCheck(BaseModel):
    """Security audit for a single HTTP cookie."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Cookie name")
    is_secure: bool = Field(description="Whether the Secure flag is present")
    is_httponly: bool = Field(description="Whether the HttpOnly flag is present")
    samesite: str | None = Field(
        default=None, description="SameSite attribute value (Strict, Lax, None)"
    )
    findings: list[str] = Field(
        default_factory=list, description="List of identified cookie issues"
    )


class WebAuditResult(BaseModel):
    """Comprehensive dynamic security inspection result for a web URL."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(description="Target URL analyzed")
    status_code: int = Field(description="HTTP response status code")
    is_plain_http: bool = Field(default=False, description="True if served over unencrypted HTTP")
    server_banner: str | None = Field(default=None, description="Disclosed Server header value")
    powered_by: str | None = Field(
        default=None, description="Disclosed X-Powered-By or framework header"
    )
    headers: dict[str, str] = Field(
        default_factory=dict, description="All normalized HTTP response headers"
    )
    header_checks: list[SecurityHeaderCheck] = Field(
        default_factory=list, description="Evaluation of standard OWASP security headers"
    )
    cookie_checks: list[CookieSecurityCheck] = Field(
        default_factory=list, description="Evaluation of security attributes in cookies"
    )
    cors_wildcard: bool = Field(
        default=False, description="True if Access-Control-Allow-Origin is configured as wildcard *"
    )
    security_score: float = Field(
        ge=0.0,
        le=10.0,
        description="Calculated web risk score (0.0 = hardened, 10.0 = severe misconfigurations)",
    )
    grade: Literal["A+", "A", "B", "C", "D", "F"] = Field(
        default="C", description="Letter grade summarizing web security posture"
    )
    owasp_tags: list[str] = Field(
        default_factory=list, description="Correlated OWASP Top 10 categories"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Tailored mitigation and hardening recommendations"
    )

    @property
    def passed_checks_count(self) -> int:
        """Count of passed security header checks."""
        return sum(1 for c in self.header_checks if c.status == "PASS")

    @property
    def total_checks_count(self) -> int:
        """Total number of security header checks performed."""
        return len(self.header_checks)
