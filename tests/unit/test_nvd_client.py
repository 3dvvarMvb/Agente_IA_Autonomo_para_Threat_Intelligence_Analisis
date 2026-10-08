"""Unit tests for NIST NVD 2.0 API client using pytest-httpx."""

import pytest
from pytest_httpx import HTTPXMock

from ti_agent.core.config import Settings
from ti_agent.models.indicator import ParsedIndicator
from ti_agent.tools.nvd import NvdClient


@pytest.mark.asyncio
async def test_nvd_cve_lookup_success(
    httpx_mock: HTTPXMock, test_settings: Settings, nvd_cve_payload: dict
) -> None:
    httpx_mock.add_response(
        url="https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2021-44228",
        json=nvd_cve_payload,
        status_code=200,
    )

    client = NvdClient(settings=test_settings)
    cve_data = await client.get_cve("CVE-2021-44228")

    assert cve_data.cve_id == "CVE-2021-44228"
    assert cve_data.severity == "CRITICAL"
    assert cve_data.score == 10.0
    assert "CWE-502" in cve_data.cwe_ids


@pytest.mark.asyncio
async def test_nvd_client_without_api_key(
    httpx_mock: HTTPXMock, nvd_cve_payload: dict
) -> None:
    no_key_settings = Settings(
        nvd_api_key=None,
        enable_cache=False,
    )
    httpx_mock.add_response(
        url="https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2021-44228",
        json=nvd_cve_payload,
        status_code=200,
    )

    client = NvdClient(settings=no_key_settings)
    assert "apiKey" not in client._get_headers()
    cve_data = await client.get_cve("cve-2021-44228")
    assert cve_data.cve_id == "CVE-2021-44228"


@pytest.mark.asyncio
async def test_nvd_dispatch_lookup(
    httpx_mock: HTTPXMock, test_settings: Settings, nvd_cve_payload: dict
) -> None:
    httpx_mock.add_response(
        url="https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2021-44228",
        json=nvd_cve_payload,
        status_code=200,
    )

    client = NvdClient(settings=test_settings)

    # CVE lookup
    res_cve = await client.lookup(ParsedIndicator.parse("CVE-2021-44228"))
    assert res_cve is not None
    assert res_cve.cve_id == "CVE-2021-44228"

    # Non-CVE lookup returns None
    res_ip = await client.lookup(ParsedIndicator.parse("8.8.8.8"))
    assert res_ip is None


@pytest.mark.asyncio
async def test_nvd_offline_mode_reads_fixture() -> None:
    offline_settings = Settings(
        offline_mode=True,
        enable_cache=False,
    )
    client = NvdClient(settings=offline_settings)
    cve_data = await client.get_cve("CVE-2021-44228")
    assert cve_data.cve_id == "CVE-2021-44228"
    assert cve_data.severity == "CRITICAL"
