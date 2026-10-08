"""Unit tests for Shodan API client using pytest-httpx."""

import pytest
from pytest_httpx import HTTPXMock

from ti_agent.core.config import Settings
from ti_agent.core.exceptions import AuthenticationError
from ti_agent.models.indicator import ParsedIndicator
from ti_agent.tools.shodan import ShodanClient


@pytest.mark.asyncio
async def test_shodan_host_lookup_success(
    httpx_mock: HTTPXMock, test_settings: Settings, shodan_ip_payload: dict
) -> None:
    httpx_mock.add_response(
        url="https://api.shodan.io/shodan/host/8.8.8.8?key=test-shodan-key-87654321",
        json=shodan_ip_payload,
        status_code=200,
    )

    client = ShodanClient(settings=test_settings)
    data = await client.get_host("8.8.8.8")

    assert data.ip == "8.8.8.8"
    assert 53 in data.ports
    assert 443 in data.ports
    assert data.org == "Google LLC"
    assert "CVE-2019-0708" in data.vulns


@pytest.mark.asyncio
async def test_shodan_host_not_found_returns_graceful_empty_model(
    httpx_mock: HTTPXMock, test_settings: Settings
) -> None:
    httpx_mock.add_response(
        url="https://api.shodan.io/shodan/host/1.2.3.4?key=test-shodan-key-87654321",
        status_code=404,
        json={"error": "No information available for that IP."},
    )

    client = ShodanClient(settings=test_settings)
    data = await client.get_host("1.2.3.4")

    assert data.ip == "1.2.3.4"
    assert data.ports == []
    assert data.vulns == []


@pytest.mark.asyncio
async def test_shodan_domain_resolution_and_lookup(
    httpx_mock: HTTPXMock, test_settings: Settings, shodan_ip_payload: dict
) -> None:
    # 1. DNS resolve
    httpx_mock.add_response(
        url="https://api.shodan.io/dns/resolve?key=test-shodan-key-87654321&hostnames=dns.google",
        json={"dns.google": "8.8.8.8"},
        status_code=200,
    )
    # 2. Host lookup
    httpx_mock.add_response(
        url="https://api.shodan.io/shodan/host/8.8.8.8?key=test-shodan-key-87654321",
        json=shodan_ip_payload,
        status_code=200,
    )

    client = ShodanClient(settings=test_settings)
    data = await client.lookup(ParsedIndicator.parse("dns.google"))

    assert data is not None
    assert data.ip == "8.8.8.8"
    assert 53 in data.ports


@pytest.mark.asyncio
async def test_shodan_401_authentication_error(
    httpx_mock: HTTPXMock, test_settings: Settings
) -> None:
    httpx_mock.add_response(
        url="https://api.shodan.io/shodan/host/8.8.8.8?key=test-shodan-key-87654321",
        status_code=401,
        json={"error": "Invalid API key"},
    )

    client = ShodanClient(settings=test_settings)
    with pytest.raises(AuthenticationError) as exc_info:
        await client.get_host("8.8.8.8")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_shodan_offline_mode_reads_fixture() -> None:
    offline_settings = Settings(
        offline_mode=True,
        enable_cache=False,
    )
    client = ShodanClient(settings=offline_settings)
    data = await client.get_host("8.8.8.8")
    assert data.ip == "8.8.8.8"
    assert 53 in data.ports
