"""
Verificador del id_token de Google (Sign in with Google / Workspace).

El frontend obtiene el `id_token` mediante Google Identity Services y lo
manda al backend en `POST /auth/login`. Aquí SOLO verificamos: firma contra
las claves públicas de Google (JWKS, gestionado por la librería oficial),
`aud` (nuestro GOOGLE_CLIENT_ID) e `iss`. No se hace ningún intercambio de
código ni se guarda ningún token de Google — es un verificador puro.

El claim `hd` (hosted domain) es lo que distingue una cuenta de Workspace de
alguno de los dominios internos del grupo (`GOOGLE_WORKSPACE_HOSTED_DOMAINS`)
de una cuenta Gmail personal (solo posible como externo-invitado vía
`invitations`). Ver docs/permisos-roles.md.
"""

from dataclasses import dataclass
from typing import Optional

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from src.shared.config import get_settings
from src.shared.errors.base import InvalidCredentialsError
from src.shared.logger import get_logger

logger = get_logger("google_oidc.verifier")


class GoogleOIDCVerificationError(InvalidCredentialsError):
    """El id_token de Google no se pudo verificar (firma, aud, iss, expirado).

    Hereda de `InvalidCredentialsError` (-> HTTP 401) a propósito: antes era
    una `Exception` a pelo, así que `error_handler` (que solo traduce
    subclases de `BaseError`) la dejaba caer en el 500 genérico — un
    id_token malformado respondía "Internal server error" en vez de "no
    autenticado" (bug detectado en la auditoría QA Fase 3)."""


@dataclass(frozen=True)
class GoogleIdentity:
    """Identidad verificada extraída del id_token de Google."""

    sub: str
    email: str
    email_verified: bool
    full_name: str
    avatar_url: Optional[str]
    hosted_domain: Optional[str]

    @property
    def is_internal(self) -> bool:
        """True si el claim `hd` (VERIFICADO por Google, nunca el sufijo del
        email) coincide con alguno de los Workspace internos configurados en
        `GOOGLE_WORKSPACE_HOSTED_DOMAINS`. Sin `hd` no hay forma de que esto
        sea True — un Gmail personal con un sufijo de email falseado no basta."""
        if not self.hosted_domain:
            return False
        settings = get_settings()
        return self.hosted_domain.lower() in settings.google_workspace_hosted_domains


class GoogleOIDCVerifier:
    """Verifica id_tokens de Google usando la librería oficial `google-auth`."""

    def verify(self, id_token_str: str) -> GoogleIdentity:
        settings = get_settings()
        if not settings.google_client_id:
            raise GoogleOIDCVerificationError(
                "Google OIDC no está configurado. Falta GOOGLE_CLIENT_ID."
            )

        try:
            payload = google_id_token.verify_oauth2_token(
                id_token_str,
                google_requests.Request(),
                audience=settings.google_client_id,
            )
        except ValueError as e:
            logger.warning("Google id_token verification failed", error=str(e))
            raise GoogleOIDCVerificationError(f"Invalid Google id_token: {e}") from e

        if payload.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise GoogleOIDCVerificationError("Unexpected issuer in Google id_token")

        email = payload.get("email")
        sub = payload.get("sub")
        if not email or not sub:
            raise GoogleOIDCVerificationError("Google id_token missing email/sub claims")

        return GoogleIdentity(
            sub=sub,
            email=email.lower(),
            email_verified=bool(payload.get("email_verified", False)),
            full_name=payload.get("name") or email.split("@")[0],
            avatar_url=payload.get("picture"),
            hosted_domain=payload.get("hd"),
        )


_verifier_instance: Optional[GoogleOIDCVerifier] = None


def get_google_oidc_verifier() -> GoogleOIDCVerifier:
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = GoogleOIDCVerifier()
    return _verifier_instance
