"""
No probamos contra Google real: mockeamos `google.oauth2.id_token.verify_oauth2_token`
(esto es lo único que valida firma/aud/iss) y comprobamos que interpretamos bien el
payload resultante, en particular la regla `hd == GOOGLE_WORKSPACE_HOSTED_DOMAIN`.
"""

import pytest

from src.shared.google_oidc.verifier import (
    GoogleOIDCVerificationError,
    GoogleOIDCVerifier,
)


@pytest.fixture(autouse=True)
def google_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_WORKSPACE_HOSTED_DOMAIN", "ameliahub.com")
    from src.shared.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _mock_payload(**overrides):
    payload = {
        "iss": "accounts.google.com",
        "sub": "1234567890",
        "email": "empleado@ameliahub.com",
        "email_verified": True,
        "name": "Empleada Amelia",
        "picture": "https://example.com/avatar.png",
        "hd": "ameliahub.com",
    }
    payload.update(overrides)
    return payload


def test_verify_returns_identity_for_internal_workspace_account(monkeypatch):
    monkeypatch.setattr(
        "src.shared.google_oidc.verifier.google_id_token.verify_oauth2_token",
        lambda *a, **k: _mock_payload(),
    )

    identity = GoogleOIDCVerifier().verify("fake-id-token")

    assert identity.email == "empleado@ameliahub.com"
    assert identity.hosted_domain == "ameliahub.com"
    assert identity.is_internal is True


def test_verify_marks_personal_gmail_as_not_internal(monkeypatch):
    monkeypatch.setattr(
        "src.shared.google_oidc.verifier.google_id_token.verify_oauth2_token",
        lambda *a, **k: _mock_payload(email="externo@gmail.com", hd=None),
    )

    identity = GoogleOIDCVerifier().verify("fake-id-token")

    assert identity.hosted_domain is None
    assert identity.is_internal is False


def test_verify_rejects_unexpected_issuer(monkeypatch):
    monkeypatch.setattr(
        "src.shared.google_oidc.verifier.google_id_token.verify_oauth2_token",
        lambda *a, **k: _mock_payload(iss="https://evil.example.com"),
    )

    with pytest.raises(GoogleOIDCVerificationError):
        GoogleOIDCVerifier().verify("fake-id-token")


def test_verify_wraps_google_valueerror(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("Token expired")

    monkeypatch.setattr(
        "src.shared.google_oidc.verifier.google_id_token.verify_oauth2_token", _raise
    )

    with pytest.raises(GoogleOIDCVerificationError):
        GoogleOIDCVerifier().verify("fake-id-token")


def test_verify_requires_client_id_configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    from src.shared.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(GoogleOIDCVerificationError):
        GoogleOIDCVerifier().verify("fake-id-token")
