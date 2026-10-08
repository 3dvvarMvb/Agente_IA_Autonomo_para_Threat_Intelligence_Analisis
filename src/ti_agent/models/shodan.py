"""Normalized Pydantic models for Shodan API telemetry."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ShodanService(BaseModel):
    """Exposed network service discovered on an open port."""

    model_config = ConfigDict(frozen=True)

    port: int = Field(description="Port number")
    transport: str = Field(default="tcp", description="Protocol transport (tcp/udp)")
    product: str | None = Field(default=None, description="Identified software product name")
    version: str | None = Field(default=None, description="Software version")
    banner_snippet: str | None = Field(default=None, description="Sanitized banner snippet")


class ShodanData(BaseModel):
    """Normalized attack surface telemetry extracted from Shodan."""

    model_config = ConfigDict(frozen=True)

    ip: str = Field(description="Queried IP address")
    ports: list[int] = Field(default_factory=list, description="List of observed open ports")
    hostnames: list[str] = Field(default_factory=list, description="Associated hostnames")
    org: str | None = Field(default=None, description="Organization name")
    isp: str | None = Field(default=None, description="Internet Service Provider")
    os: str | None = Field(default=None, description="Operating system")
    asn: str | None = Field(default=None, description="Autonomous System Number")
    vulns: list[str] = Field(default_factory=list, description="Associated CVE vulnerabilities")
    tags: list[str] = Field(default_factory=list, description="Shodan classification tags")
    services: list[ShodanService] = Field(
        default_factory=list, description="Detailed open services"
    )
    last_update: str | None = Field(default=None, description="Last update timestamp string")

    @property
    def has_known_vulnerabilities(self) -> bool:
        """True if any CVEs are associated with this host in Shodan."""
        return len(self.vulns) > 0

    @classmethod
    def from_api_response(cls, ip: str, raw_json: dict[str, Any]) -> "ShodanData":
        """Factory method to transform Shodan host lookup JSON into normalized model."""
        services: list[ShodanService] = []
        raw_services = raw_json.get("data", [])

        if isinstance(raw_services, list):
            for svc in raw_services:
                if not isinstance(svc, dict):
                    continue
                port = svc.get("port")
                if port is None:
                    continue

                banner = svc.get("data")
                banner_str = None
                if isinstance(banner, str):
                    # Sanitize and truncate banner snippet for safety
                    cleaned = " ".join(banner.split())[:120]
                    banner_str = cleaned if cleaned else None

                services.append(
                    ShodanService(
                        port=int(port),
                        transport=str(svc.get("transport", "tcp")),
                        product=svc.get("product"),
                        version=svc.get("version"),
                        banner_snippet=banner_str,
                    )
                )

        ports = [int(p) for p in raw_json.get("ports", []) if isinstance(p, (int, str))]
        hostnames = [str(h) for h in raw_json.get("hostnames", []) if isinstance(h, str)]
        vulns = [str(v).upper() for v in raw_json.get("vulns", []) if isinstance(v, str)]
        tags = [str(t) for t in raw_json.get("tags", []) if isinstance(t, str)]

        return cls(
            ip=ip,
            ports=sorted(set(ports)),
            hostnames=hostnames,
            org=raw_json.get("org"),
            isp=raw_json.get("isp"),
            os=raw_json.get("os"),
            asn=raw_json.get("asn"),
            vulns=vulns,
            tags=tags,
            services=services,
            last_update=raw_json.get("last_update"),
        )
