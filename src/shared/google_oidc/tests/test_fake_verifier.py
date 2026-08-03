"""
El verificador falso es un bypass del control de acceso: lo que se prueba aquí
no es solo que funcione, sino que NO se pueda activar en un entorno desplegado
y que siga rechazando basura igual que el real.
"""

import base64
import json

import pytest

from src.shared.google_oidc.factory import (
    get_google_oidc_verifier,
    reset_google_oidc_verifier,
)
from src.shared.google_oidc.fake_verifier import (
    FAKE_TOKEN_PREFIX,
    FakeGoogleOIDCVerifier,
    build_fake_id_token,
)
from src.shared.google_oidc.verifier import (
    GoogleOIDCVerificationError,
    GoogleOIDCVerifier,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    """`get_settings` está cacheado con `lru_cache` y el verificador es un
    singleton: sin limpiar ambos, el primer test de este módulo decidiría la
    configuración de todos los demás."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_WORKSPACE_HOSTED_DOMAINS", "ameliahub.com,octocam-maps.com")
    monkeypatch.delenv("GOOGLE_WORKSPACE_HOSTED_DOMAIN", raising=False)
    from src.shared.config import get_settings

    get_settings.cache_clear()
    reset_google_oidc_verifier()
    yield
    get_settings.cache_clear()
    reset_google_oidc_verifier()


# --- Formato y parseo -------------------------------------------------------


def test_build_and_verify_round_trip_for_internal_account():
    token = build_fake_id_token(
        sub="e2e-admin",
        email="People@AmeliaHub.com",
        full_name="Beatriz Luna",
        avatar_url="https://example.com/avatar.png",
        hosted_domain="ameliahub.com",
    )

    identity = FakeGoogleOIDCVerifier().verify(token)

    assert identity.sub == "e2e-admin"
    # Igual que el real: el email se normaliza a minúsculas.
    assert identity.email == "people@ameliahub.com"
    assert identity.email_verified is True
    assert identity.full_name == "Beatriz Luna"
    assert identity.avatar_url == "https://example.com/avatar.png"
    assert identity.hosted_domain == "ameliahub.com"


def test_identity_is_internal_when_hosted_domain_matches_workspace():
    token = build_fake_id_token(
        sub="e2e-empleado", email="empleado@ameliahub.com", hosted_domain="ameliahub.com"
    )

    assert FakeGoogleOIDCVerifier().verify(token).is_internal is True


def test_identity_is_not_internal_without_hosted_domain():
    """Un Gmail personal (sin claim `hd`) — la vía del externo-invitado, que
    exige invitación pendiente en `LoginWithGoogleUseCase`."""
    token = build_fake_id_token(sub="e2e-externo", email="invitado@gmail.com")

    assert FakeGoogleOIDCVerifier().verify(token).is_internal is False


def test_full_name_falls_back_to_email_local_part():
    token = build_fake_id_token(sub="e2e-1", email="sin.nombre@ameliahub.com")

    assert FakeGoogleOIDCVerifier().verify(token).full_name == "sin.nombre"


def test_email_verified_false_is_preserved():
    """El caso de uso rechaza `email_verified=False`; el fake tiene que poder
    reproducirlo para que ese camino sea testeable en E2E."""
    token = build_fake_id_token(
        sub="e2e-1", email="nuevo@ameliahub.com", email_verified=False
    )

    assert FakeGoogleOIDCVerifier().verify(token).email_verified is False


# --- Rechazos: mismo contrato de error que el verificador real --------------


@pytest.mark.parametrize(
    "bad_token",
    [
        pytest.param("", id="vacio"),
        pytest.param("eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.firma", id="jwt-de-verdad"),
        pytest.param("fake-google-id-token", id="prefijo-sin-punto"),
        pytest.param(f"{FAKE_TOKEN_PREFIX}no-es-base64!!!", id="base64-invalido"),
    ],
)
def test_rejects_tokens_that_are_not_synthetic(bad_token):
    with pytest.raises(GoogleOIDCVerificationError):
        FakeGoogleOIDCVerifier().verify(bad_token)


def test_rejects_payload_that_is_not_a_json_object():
    encoded = base64.urlsafe_b64encode(b'"solo-un-string"').decode().rstrip("=")

    with pytest.raises(GoogleOIDCVerificationError):
        FakeGoogleOIDCVerifier().verify(f"{FAKE_TOKEN_PREFIX}{encoded}")


@pytest.mark.parametrize("missing", ["sub", "email"])
def test_rejects_payload_missing_required_claims(missing):
    payload = {"sub": "e2e-1", "email": "x@ameliahub.com", "email_verified": True}
    del payload[missing]
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    with pytest.raises(GoogleOIDCVerificationError):
        FakeGoogleOIDCVerifier().verify(f"{FAKE_TOKEN_PREFIX}{encoded}")


# --- Factoría ---------------------------------------------------------------


def test_factory_returns_real_verifier_by_default(monkeypatch):
    monkeypatch.delenv("GOOGLE_OIDC_PROVIDER", raising=False)
    from src.shared.config import get_settings

    get_settings.cache_clear()

    assert isinstance(get_google_oidc_verifier(), GoogleOIDCVerifier)


def test_factory_returns_fake_verifier_when_configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_OIDC_PROVIDER", "fake")
    from src.shared.config import get_settings

    get_settings.cache_clear()

    assert isinstance(get_google_oidc_verifier(), FakeGoogleOIDCVerifier)


def test_factory_rejects_unknown_provider(monkeypatch):
    """Un typo (`faker`) no debe caer al verificador real en silencio ni, peor,
    al falso."""
    monkeypatch.setenv("GOOGLE_OIDC_PROVIDER", "faker")
    from src.shared.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(NotImplementedError):
        get_google_oidc_verifier()


# --- Contención: el arranque debe abortar fuera de local -------------------


@pytest.mark.parametrize("environment", ["prod", "production", "stage", "staging"])
def test_settings_abort_when_fake_verifier_in_protected_environment(
    monkeypatch, environment
):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("GOOGLE_OIDC_PROVIDER", "fake")
    # Todo lo demás correcto, para aislar que el motivo del fallo es el provider.
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("REFRESH_TOKEN_COOKIE_SECURE", "false")
    monkeypatch.setenv("CORS_ORIGINS", "https://intranet.ameliahub.com")
    from src.shared.config import Settings

    with pytest.raises(RuntimeError, match="GOOGLE_OIDC_PROVIDER"):
        Settings()


def test_settings_abort_when_fake_verifier_with_secure_cookie(monkeypatch):
    """Segunda barrera, independiente de ENVIRONMENT: si la cookie de refresh
    es Secure, se está sirviendo por HTTPS y eso no es un entorno local —
    aunque alguien haya olvidado exportar ENVIRONMENT."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("GOOGLE_OIDC_PROVIDER", "fake")
    monkeypatch.setenv("REFRESH_TOKEN_COOKIE_SECURE", "true")
    from src.shared.config import Settings

    with pytest.raises(RuntimeError, match="REFRESH_TOKEN_COOKIE_SECURE"):
        Settings()


def test_settings_allow_fake_verifier_in_local_dev(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("GOOGLE_OIDC_PROVIDER", "fake")
    monkeypatch.setenv("REFRESH_TOKEN_COOKIE_SECURE", "false")
    from src.shared.config import Settings

    assert Settings().google_oidc_provider == "fake"
