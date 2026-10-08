"""Unit tests for VirusTotal API client using pytest-httpx."""

import pytest
from pytest_httpx import HTTPXMock

from ti_agent.core.config import Settings
from ti_agent.core.exceptions import (
    AuthenticationError,
    RateLimitExceededError,
    ResourceNotFoundError,
)
from ti_agent.models.indicator import ParsedIndicator
from ti_agent.tools.virustotal import VirusTotalClient


@pytest.mark.asyncio
async def test_virustotal_ip_lookup_success(
    httpx_mock: HTTPXMock, test_settings: Settings, vt_ip_payload: dict
) -> None:
    httpx_mock.add_response(
        url="https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8",
        json=vt_ip_payload,
        status_code=200,
    )

    client = VirusTotalClient(settings=test_settings)
    report = await client.get_ip_report("8.8.8.8")

    assert report.target == "8.8.8.8"
    assert report.reputation == 85
    assert report.as_owner == "Google LLC"


@pytest.mark.asyncio
async def test_virustotal_domain_lookup_success(
    httpx_mock: HTTPXMock, test_settings: Settings, vt_domain_payload: dict
) -> None:
    httpx_mock.add_response(
        url="https://www.virustotal.com/api/v3/domains/c2-malicious-traffic.net",
        json=vt_domain_payload,
        status_code=200,
    )

    client = VirusTotalClient(settings=test_settings)
    report = await client.get_domain_report("c2-malicious-traffic.net")

    assert report.target == "c2-malicious-traffic.net"
    assert report.is_flagged_malicious is True


@pytest.mark.asyncio
async def test_virustotal_hash_lookup_success(
    httpx_mock: HTTPXMock, test_settings: Settings, vt_hash_payload: dict
) -> None:
    file_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    httpx_mock.add_response(
        url=f"https://www.virustotal.com/api/v3/files/{file_hash}",
        json=vt_hash_payload,
        status_code=200,
    )

    client = VirusTotalClient(settings=test_settings)
    report = await client.get_file_report(file_hash)

    assert report.meaningful_name == "ransomware_payload.exe"
    assert report.stats.malicious == 65


@pytest.mark.asyncio
async def test_virustotal_dispatch_lookup(
    httpx_mock: HTTPXMock, test_settings: Settings, vt_ip_payload: dict
) -> None:
    httpx_mock.add_response(
        url="https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8",
        json=vt_ip_payload,
        status_code=200,
    )

    client = VirusTotalClient(settings=test_settings)

    # 1. IP
    res_ip = await client.lookup(ParsedIndicator.parse("8.8.8.8"))
    assert res_ip is not None
    assert res_ip.target == "8.8.8.8"

    # 2. CVE should return None (not supported on VT)
    res_cve = await client.lookup(ParsedIndicator.parse("CVE-2021-44228"))
    assert res_cve is None


@pytest.mark.asyncio
async def test_virustotal_401_authentication_error(
    httpx_mock: HTTPXMock, test_settings: Settings
) -> None:
    httpx_mock.add_response(
        url="https://www.virustotal.com/api/v3/ip_addresses/1.2.3.4",
        status_code=401,
        text="Wrong API key",
    )

    client = VirusTotalClient(settings=test_settings)
    with pytest.raises(AuthenticationError) as exc_info:
        await client.get_ip_report("1.2.3.4")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_virustotal_404_not_found(
    httpx_mock: HTTPXMock, test_settings: Settings
) -> None:
    httpx_mock.add_response(
        url="https://www.virustotal.com/api/v3/ip_addresses/1.2.3.4",
        status_code=404,
        text="Not Found",
    )

    client = VirusTotalClient(settings=test_settings)
    with pytest.raises(ResourceNotFoundError) as exc_info:
        await client.get_ip_report("1.2.3.4")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_virustotal_429_rate_limit(
    httpx_mock: HTTPXMock, test_settings: Settings
) -> None:
    # Simulates 3 consecutive 429 responses
    for _ in range(3):
        httpx_mock.add_response(
            url="https://www.virustotal.com/api/v3/ip_addresses/1.2.3.4",
            status_code=429,
            text="Quota Exceeded",
        )

    client = VirusTotalClient(settings=test_settings)
    with pytest.raises(RateLimitExceededError):
        await client.get_ip_report("1.2.3.4")


@pytest.mark.asyncio
async def test_virustotal_offline_mode_reads_fixture() -> None:
    offline_settings = Settings(
        offline_mode=True,
        enable_cache=False,
    )
    client = VirusTotalClient(settings=offline_settings)
    report = await client.get_ip_report("8.8.8.8")
    assert report.target == "8.8.8.8"
    assert report.reputation == 85
