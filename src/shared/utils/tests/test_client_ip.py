"""
SEC-1 (auditoría QA Fase 3): `get_client_ip` NO debe confiar en
X-Forwarded-For/X-Real-IP salvo que la conexión directa venga de un proxy en
`TRUSTED_PROXY_IPS` — de lo contrario cualquier cliente falsea su IP y se
salta el rate-limit del login o falsea auth_sessions.ip_address.
"""

from types import SimpleNamespace

import pytest

from src.shared.utils.client_ip import get_client_ip


def _request(*, direct_ip: str, headers: dict | None = None):
    return SimpleNamespace(
        client=SimpleNamespace(host=direct_ip) if direct_ip else None,
        headers=headers or {},
    )


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch):
    from src.shared.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ignores_forwarded_headers_when_no_trusted_proxies(monkeypatch):
    """Allowlist vacía (default) -> XFF/X-Real-IP se ignoran, aunque el
    atacante los mande, y se usa siempre la IP de la conexión TCP real."""
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    request = _request(
        direct_ip="203.0.113.9",
        headers={"x-forwarded-for": "1.2.3.4", "x-real-ip": "5.6.7.8"},
    )

    assert get_client_ip(request) == "203.0.113.9"


def test_ignores_forwarded_headers_from_untrusted_direct_ip(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.1")
    request = _request(direct_ip="203.0.113.9", headers={"x-forwarded-for": "1.2.3.4"})

    assert get_client_ip(request) == "203.0.113.9"


def test_trusts_forwarded_for_from_allowlisted_proxy(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.1,10.0.0.2")
    request = _request(
        direct_ip="10.0.0.1",
        headers={"x-forwarded-for": "1.2.3.4, 10.0.0.1"},
    )

    assert get_client_ip(request) == "1.2.3.4"


def test_trusts_real_ip_from_allowlisted_proxy_without_forwarded_for(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.1")
    request = _request(direct_ip="10.0.0.1", headers={"x-real-ip": "1.2.3.4"})

    assert get_client_ip(request) == "1.2.3.4"


def test_falls_back_to_direct_ip_when_no_client(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    request = _request(direct_ip="")

    assert get_client_ip(request) == "unknown"
