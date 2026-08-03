"""
Verificador FALSO del id_token de Google — solo para desarrollo y E2E local.

## Por qué existe

`POST /auth/login` es el único punto de entrada de sesión y exige un id_token
firmado por Google. Automatizar el login real de Google desde un navegador
controlado (Playwright) no es viable: 2FA, detección de automatización y
captchas lo hacen frágil e irreproducible. Sin este adaptador NO hay E2E
autenticados de ningún rol.

## Formato del token sintético

`fake-google-id-token.<base64url(JSON)>` — el prefijo es obligatorio y hace
imposible confundirlo con un JWT real (un JWT empieza por `eyJ`). El JSON
admite las mismas claves que el payload de Google:

    {"sub": "e2e-admin", "email": "people@ameliahub.com",
     "email_verified": true, "name": "Beatriz Luna", "hd": "ameliahub.com"}

`hd` es lo que decide si la identidad es interna (auto-provisión como
`empleado`) o externa (necesita invitación) — ver `GoogleIdentity.is_internal`
y `LoginWithGoogleUseCase`. Omitirlo simula un Gmail personal.

Todo lo que no encaje con el formato se rechaza con la MISMA excepción que el
verificador real (`GoogleOIDCVerificationError` -> HTTP 401), para que los
tests de "credencial inválida" sigan siendo válidos con este adaptador puesto.

## Contención

- `Settings._enforce_secure_defaults` aborta el arranque si
  `GOOGLE_OIDC_PROVIDER != "google"` en prod/stage, o si la cookie de refresh
  es Secure (señal de HTTPS) en cualquier entorno.
- Cada verificación deja un log de nivel CRITICAL. Si esto aparece en los
  logs de un entorno que no sea el portátil de alguien, es un incidente.
"""

import base64
import binascii
import json

from src.shared.logger import get_logger

from .verifier import GoogleIdentity, GoogleOIDCVerificationError

logger = get_logger("google_oidc.fake_verifier")

FAKE_TOKEN_PREFIX = "fake-google-id-token."


def build_fake_id_token(
    *,
    sub: str,
    email: str,
    email_verified: bool = True,
    full_name: str | None = None,
    avatar_url: str | None = None,
    hosted_domain: str | None = None,
) -> str:
    """Construye un id_token sintético. Lo usan los tests y el helper de E2E.

    Vive aquí (junto al parser) para que formato y constructor no puedan
    divergir: si cambia uno, el otro está en el mismo fichero.
    """
    payload: dict[str, object] = {
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
    }
    if full_name is not None:
        payload["name"] = full_name
    if avatar_url is not None:
        payload["picture"] = avatar_url
    if hosted_domain is not None:
        payload["hd"] = hosted_domain

    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{FAKE_TOKEN_PREFIX}{encoded}"


class FakeGoogleOIDCVerifier:
    """Decodifica el id_token sintético sin verificar ninguna firma.

    Implementa `IGoogleIdentityVerifier` (duck typing estructural) y devuelve
    la MISMA dataclass `GoogleIdentity` que el verificador real, para que
    `is_internal` y el caso de uso se comporten exactamente igual.
    """

    def verify(self, id_token_str: str) -> GoogleIdentity:
        if not id_token_str or not id_token_str.startswith(FAKE_TOKEN_PREFIX):
            raise GoogleOIDCVerificationError(
                "Invalid Google id_token: se esperaba un token sintético "
                f"con el prefijo '{FAKE_TOKEN_PREFIX}' "
                "(GOOGLE_OIDC_PROVIDER=fake)."
            )

        encoded = id_token_str[len(FAKE_TOKEN_PREFIX) :]
        # base64url sin padding: se repone antes de decodificar.
        padding = "=" * (-len(encoded) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        except (binascii.Error, ValueError) as e:
            raise GoogleOIDCVerificationError(
                f"Invalid Google id_token: payload sintético ilegible ({e})."
            ) from e

        if not isinstance(payload, dict):
            raise GoogleOIDCVerificationError(
                "Invalid Google id_token: el payload sintético debe ser un objeto JSON."
            )

        email = payload.get("email")
        sub = payload.get("sub")
        if not email or not sub:
            raise GoogleOIDCVerificationError(
                "Google id_token missing email/sub claims"
            )

        logger.critical(
            "FAKE Google OIDC verifier en uso — la firma del id_token NO se ha "
            "verificado. Esto SOLO es admisible en desarrollo/E2E local.",
            email=email,
            sub=sub,
        )

        return GoogleIdentity(
            sub=str(sub),
            email=str(email).lower(),
            email_verified=bool(payload.get("email_verified", False)),
            full_name=payload.get("name") or str(email).split("@")[0],
            avatar_url=payload.get("picture"),
            hosted_domain=payload.get("hd"),
        )
