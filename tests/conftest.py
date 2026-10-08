"""Shared pytest configuration, mock fixtures, and environment setup."""

import json
from pathlib import Path

import pytest

from ti_agent.core.config import Settings


@pytest.fixture(autouse=True)
def test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate testing environment with dummy keys and temporary directories."""
    monkeypatch.setenv("VT_API_KEY", "test-vt-api-key-12345678")
    monkeypatch.setenv("SHODAN_API_KEY", "test-shodan-api-key-12345678")
    monkeypatch.setenv("NVD_API_KEY", "test-nvd-api-key-12345678")
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ENABLE_CACHE", "false")
    monkeypatch.setenv("OFFLINE_MODE", "false")


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Provide explicit settings instance for unit testing with cache disabled."""
    return Settings(
        vt_api_key="test-vt-key-87654321",
        shodan_api_key="test-shodan-key-87654321",
        nvd_api_key="test-nvd-key-87654321",
        cache_dir=tmp_path / "cache",
        enable_cache=False,
        offline_mode=False,
    )


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to project fixtures directory."""
    return Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def vt_ip_payload(fixtures_dir: Path) -> dict:
    with open(fixtures_dir / "virustotal_ip.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def vt_domain_payload(fixtures_dir: Path) -> dict:
    with open(fixtures_dir / "virustotal_domain.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def vt_hash_payload(fixtures_dir: Path) -> dict:
    with open(fixtures_dir / "virustotal_hash.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def shodan_ip_payload(fixtures_dir: Path) -> dict:
    with open(fixtures_dir / "shodan_ip.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def nvd_cve_payload(fixtures_dir: Path) -> dict:
    with open(fixtures_dir / "nvd_cve.json", encoding="utf-8") as f:
        return json.load(f)
