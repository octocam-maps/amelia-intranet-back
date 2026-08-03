"""Factoría de `IGoogleIdentityVerifier` según `settings.google_oidc_provider`."""

from typing import Optional, Union

from src.shared.config import get_settings
from src.shared.logger import get_logger

from .fake_verifier import FakeGoogleOIDCVerifier
from .verifier import GoogleOIDCVerifier

logger = get_logger("google_oidc.factory")

_verifier_instance: Optional[Union[GoogleOIDCVerifier, FakeGoogleOIDCVerifier]] = None


def get_google_oidc_verifier() -> Union[GoogleOIDCVerifier, FakeGoogleOIDCVerifier]:
    """`"google"` (default) verifica la firma real contra el JWKS de Google;
    `"fake"` acepta un id_token sintético sin firma — SOLO desarrollo y E2E,
    con el arranque bloqueado en prod/stage por `_enforce_secure_defaults`.
    Cualquier otro valor falla explícitamente en vez de caer al real en
    silencio (un typo como `GOOGLE_OIDC_PROVIDER=faker` debe romper, no
    ignorarse)."""
    global _verifier_instance
    if _verifier_instance is not None:
        return _verifier_instance

    provider = get_settings().google_oidc_provider
    if provider == "google":
        _verifier_instance = GoogleOIDCVerifier()
    elif provider == "fake":
        logger.critical(
            "GOOGLE_OIDC_PROVIDER=fake — el login acepta id_tokens sintéticos "
            "SIN verificar firma. Exclusivo de desarrollo y E2E en local."
        )
        _verifier_instance = FakeGoogleOIDCVerifier()
    else:
        raise NotImplementedError(
            f"GOOGLE_OIDC_PROVIDER='{provider}' no está implementado — "
            "usa 'google' (default) o 'fake' (solo dev/E2E)."
        )

    return _verifier_instance


def reset_google_oidc_verifier() -> None:
    """Descarta el singleton. Necesario en tests que cambian
    `GOOGLE_OIDC_PROVIDER` con monkeypatch: sin esto, el primer test fija el
    adaptador para todos los demás."""
    global _verifier_instance
    _verifier_instance = None
