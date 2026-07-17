"""
No probamos contra Google real: mockeamos `google.oauth2.id_token.verify_oauth2_token`
(esto es lo único que valida firma/aud/iss) y comprobamos que interpretamos bien el
payload resultante, en particular la regla
`hd in GOOGLE_WORKSPACE_HOSTED_DOMAINS` (CSV, soporta más de un Workspace interno).
"""

import pytest

from src.shared.google_oidc.verifier import (
    GoogleOIDCVerificationError,
    GoogleOIDCVerifier,
)


@pytest.fixture(autouse=True)
def google_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    # Dos Workspace internos configurados (ver GOOGLE_WORKSPACE_HOSTED_DOMAINS
    # en config.py) — ejercita explícitamente el caso multi-dominio.
    monkeypatch.setenv("GOOGLE_WORKSPACE_HOSTED_DOMAINS", "ameliahub.com,octocam-maps.com")
    monkeypatch.delenv("GOOGLE_WORKSPACE_HOSTED_DOMAIN", raising=False)
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


def test_verify_marks_second_internal_workspace_domain_as_internal(monkeypatch):
    """octocam-maps.com se agrega como segundo dominio interno (además de
    ameliahub.com) sin tocar código, solo GOOGLE_WORKSPACE_HOSTED_DOMAINS."""
    monkeypatch.setattr(
        "src.shared.google_oidc.verifier.google_id_token.verify_oauth2_token",
        lambda *a, **k: _mock_payload(
            email="empleado@octocam-maps.com", hd="octocam-maps.com"
        ),
    )

    identity = GoogleOIDCVerifier().verify("fake-id-token")

    assert identity.hosted_domain == "octocam-maps.com"
    assert identity.is_internal is True


def test_verify_marks_unlisted_hosted_domain_as_not_internal(monkeypatch):
    """Un `hd` verificado que NO está en GOOGLE_WORKSPACE_HOSTED_DOMAINS no es
    interno — solo entra vía `invitations` (NotInvitedError si no la hay,
    ver LoginWithGoogleUseCase)."""
    monkeypatch.setattr(
        "src.shared.google_oidc.verifier.google_id_token.verify_oauth2_token",
        lambda *a, **k: _mock_payload(
            email="socio@otra-empresa.com", hd="otra-empresa.com"
        ),
    )

    identity = GoogleOIDCVerifier().verify("fake-id-token")

    assert identity.hosted_domain == "otra-empresa.com"
    assert identity.is_internal is False


def test_verify_cannot_be_spoofed_via_email_suffix_without_matching_hd(monkeypatch):
    """El sufijo del email NUNCA decide `is_internal` — solo el claim `hd`
    verificado por Google. Un email con sufijo @octocam-maps.com pero sin
    `hd` (p.ej. reenviado a una cuenta Gmail personal, o `hd` ausente) no
    debe colarse como interno."""
    monkeypatch.setattr(
        "src.shared.google_oidc.verifier.google_id_token.verify_oauth2_token",
        lambda *a, **k: _mock_payload(email="falso@octocam-maps.com", hd=None),
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
