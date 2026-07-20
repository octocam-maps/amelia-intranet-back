"""
Configuración centralizada leída de variables de entorno.
Un único punto de lectura para evitar `os.getenv` disperso por el código.
"""

import os
from functools import lru_cache


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


# Entornos donde un default inseguro NO es tolerable: el arranque debe abortar
# (fail-fast) en vez de dejar que un olvido de configuración se convierta en
# una brecha. En `dev`/`test` los defaults cómodos siguen valiendo.
_SECURE_ENVIRONMENTS = {"prod", "production", "stage", "staging"}
_INSECURE_JWT_SECRET_DEFAULT = "change-me-in-production"
_MIN_JWT_SECRET_LENGTH = 32


class Settings:
    def __init__(self) -> None:
        self.environment = os.getenv("ENVIRONMENT", "dev")
        # Swagger/Redoc/openapi.json exponen el contrato completo de la API
        # (rutas, esquemas, hasta ejemplos) — cómodo en dev, pero un default
        # `true` en cualquier entorno lo deja abierto también en prod/stage si
        # nadie lo desactiva a mano (bug real, auditoría QA). Default: solo
        # `dev`/`test` lo activan; el resto lo desactiva salvo override
        # explícito con `SWAGGER_ENABLED=true`.
        _default_swagger_enabled = self.environment in {"dev", "test"}
        self.swagger_enabled = _is_truthy(
            os.getenv("SWAGGER_ENABLED", str(_default_swagger_enabled))
        )

        self.database_url = os.getenv(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:5436/postgres"
        )

        self.cors_origins = [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ]

        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_access_token_expire_minutes = int(
            os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
        )
        self.jwt_refresh_token_expire_days = int(
            os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
        )

        self.refresh_token_cookie_name = os.getenv(
            "REFRESH_TOKEN_COOKIE_NAME", "amelia_intranet_refresh_token"
        )
        # `/auth` (no `/auth/refresh`): el navegador solo adjunta la cookie a
        # rutas que empiecen por su `path`. Con `/auth/refresh` la cookie
        # NUNCA llegaba a `/auth/logout`, así que `LogoutUseCase` no podía
        # revocar nada server-side (bug real detectado en el E2E de Fase 1 —
        # ver SOFT-2170). `/auth` cubre `/auth/refresh` y `/auth/logout`
        # sin exponer la cookie a rutas fuera de auth.
        self.refresh_token_cookie_path = os.getenv("REFRESH_TOKEN_COOKIE_PATH", "/auth")
        # Secure por defecto en entornos protegidos (HTTPS); en dev se permite
        # HTTP local. Un override explícito a `false` en prod/stage lo rechaza
        # el guardia de `_enforce_secure_defaults`.
        _default_cookie_secure = (
            "true" if self.environment in _SECURE_ENVIRONMENTS else "false"
        )
        self.refresh_token_cookie_secure = _is_truthy(
            os.getenv("REFRESH_TOKEN_COOKIE_SECURE", _default_cookie_secure)
        )

        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")

        # Dominios de Google Workspace considerados "internos" — determinan
        # quién puede auto-provisionarse como `empleado` sin invitación (ver
        # LoginWithGoogleUseCase e IGoogleIdentityVerifier.is_internal). CSV
        # para soportar más de una entidad del grupo Amelia con Workspace
        # propio (p.ej. ameliahub.com + octocam-maps.com) sin tocar código.
        #
        # Retrocompatibilidad: si la variable plural no está seteada, se cae
        # a la singular histórica `GOOGLE_WORKSPACE_HOSTED_DOMAIN` (Fase 1)
        # para no romper despliegues/CI que todavía la exporten.
        _raw_hosted_domains = os.getenv("GOOGLE_WORKSPACE_HOSTED_DOMAINS")
        if _raw_hosted_domains is None:
            _raw_hosted_domains = os.getenv(
                "GOOGLE_WORKSPACE_HOSTED_DOMAIN", "ameliahub.com"
            )
        # Normalizados a minúsculas: el claim `hd` de Google es un hostname,
        # que se compara sin distinguir mayúsculas/minúsculas.
        self.google_workspace_hosted_domains = frozenset(
            domain.strip().lower()
            for domain in _raw_hosted_domains.split(",")
            if domain.strip()
        )

        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")
        self.sendgrid_from_email = os.getenv("SENDGRID_FROM_EMAIL", "no-reply@ameliahub.com")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

        # Vigencia de una invitación (`invitations.expires_at`, feature
        # `staff`/`invitations`) antes de que "Reenviar" tenga que extenderla.
        # `token` se guarda pero no se usa en ningún enlace (el acceso sigue
        # siendo 100% Google OIDC) — este plazo solo acota cuánto tiempo se
        # sigue considerando "pendiente" una invitación sin aceptar.
        self.invitation_expires_days = int(os.getenv("INVITATION_EXPIRES_DAYS", "7"))

        # Fase 6 (notificaciones): "mock" (default) escribe en `email_log` sin
        # ninguna llamada de red; "sendgrid" envía de verdad vía la API v3 de
        # SendGrid (requiere `SENDGRID_API_KEY` y `SENDGRID_FROM_EMAIL`
        # verificado). Ver src/shared/email/infrastructure/factory.py.
        self.email_provider = os.getenv("EMAIL_PROVIDER", "mock")

        # Fase 4 v2 (documentos, Google Drive real): "mock" (default) guarda
        # el binario en memoria del proceso, sin red ni credenciales; "google"
        # es el proveedor real (Service Account + Domain-Wide Delegation).
        # Ver src/features/documents/infrastructure/factory.py.
        self.drive_provider = os.getenv("DRIVE_PROVIDER", "mock")

        # Carpeta raíz de Drive bajo la que viven las subcarpetas por
        # empleado (nombre = email). Solo se usa con DRIVE_PROVIDER=google.
        self.drive_root_folder_id = os.getenv("DRIVE_ROOT_FOLDER_ID", "")

        # SIN USO desde la decisión posterior del usuario de acceder a Drive
        # vía Unidad compartida (Shared Drive) en vez de Domain-Wide
        # Delegation (ver engram #450 y `GoogleDriveDocumentStorage`/
        # `google_drive_client.build_credentials`, WU-B): la Service Account
        # entra DIRECTAMENTE como miembro de la Shared Drive, sin
        # `with_subject`/impersonación. Se conserva la variable (no se lee en
        # ningún punto del código) para no romper despliegues que ya la
        # exporten; puede eliminarse en una limpieza posterior.
        self.drive_impersonate_subject = os.getenv("DRIVE_IMPERSONATE_SUBJECT", "")

        # Credenciales de la Service Account: ruta a un fichero JSON en disco,
        # o el JSON completo inline (útil en despliegues sin filesystem de
        # secretos, p. ej. una variable de entorno gestionada). Se acepta
        # cualquiera de las dos; el adaptador real (WU-B) decide cuál usar.
        self.google_service_account_key_path = os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_KEY_PATH", ""
        )
        self.google_service_account_key_json = os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_KEY_JSON", ""
        )

        # Tamaño máximo admitido por documento (nóminas/contratos suelen ser
        # pequeños). Acota tanto la subida manual como qué archivos concilia
        # el sync — sin este límite, el patrón "buffer completo en memoria"
        # de la descarga (ver design) podría recibir un PDF enorme colocado
        # a mano en Drive fuera de la app.
        self.documents_max_upload_mb = int(os.getenv("DOCUMENTS_MAX_UPLOAD_MB", "10"))

        # Nager.Date (https://date.nager.at) — festivos oficiales de España
        # para la importación automática de Festivos (Fase 6, ronda 2).
        # Configurable para poder apuntar a un stub en tests/staging sin
        # tocar código.
        self.nager_base_url = os.getenv("NAGER_BASE_URL", "https://date.nager.at")

        # IPs del proxy inverso en las que SÍ confiamos para leer
        # X-Forwarded-For/X-Real-IP (ver src/shared/utils/client_ip.py). Vacío
        # por defecto: sin esta allowlist, cualquier cliente podría falsear su
        # IP con esas cabeceras y saltarse el rate-limit del login o falsear
        # auth_sessions.ip_address / document_signatures.ip_address. Decisión
        # del usuario: por ahora se despliega directo (sin proxy delante), así
        # que queda vacía hasta que haya un balanceador/proxy real que la use.
        self.trusted_proxy_ips = {
            ip.strip()
            for ip in os.getenv("TRUSTED_PROXY_IPS", "").split(",")
            if ip.strip()
        }

        self._enforce_secure_defaults()

    def _enforce_secure_defaults(self) -> None:
        """Fail-fast en entornos protegidos (prod/stage): un default inseguro
        olvidado en el despliegue no debe convertir un error de configuración
        en una brecha. Se acumulan TODOS los problemas para reportarlos juntos,
        no solo el primero."""
        if self.environment not in _SECURE_ENVIRONMENTS:
            return

        problems: list[str] = []

        # JWT_SECRET_KEY firma access y refresh tokens. Con el default público
        # (o un secreto trivialmente corto) cualquiera podría forjar un JWT con
        # role="administrador" y el `sub` de cualquier usuario.
        if (
            self.jwt_secret_key == _INSECURE_JWT_SECRET_DEFAULT
            or len(self.jwt_secret_key) < _MIN_JWT_SECRET_LENGTH
        ):
            problems.append(
                "JWT_SECRET_KEY sin configurar o demasiado corto "
                f"(mínimo {_MIN_JWT_SECRET_LENGTH} caracteres aleatorios). "
                "Con el valor por defecto se pueden forjar tokens."
            )

        # La cookie del refresh token (credencial de 7 días) debe viajar solo
        # por HTTPS. El default ya es Secure aquí, pero un override explícito a
        # false reintroduce el riesgo de interceptación en un downgrade a HTTP.
        if not self.refresh_token_cookie_secure:
            problems.append(
                "REFRESH_TOKEN_COOKIE_SECURE=false: la cookie de refresh "
                "viajaría sin el flag Secure (interceptable sobre HTTP)."
            )

        # CORS con wildcard + credenciales (cookies) habilitadas es una
        # combinación insegura: `allow_credentials=True` es fijo en este
        # proyecto (ver `main.py`), así que un `CORS_ORIGINS=*` olvidado en
        # el despliegue dejaría cualquier origen leer respuestas autenticadas
        # con la cookie de refresh adjunta.
        if "*" in self.cors_origins:
            problems.append(
                "CORS_ORIGINS incluye '*' junto con allow_credentials=True: "
                "cualquier origen podría hacer peticiones autenticadas con "
                "la cookie de refresh."
            )

        if problems:
            detail = "\n".join(f"  - {p}" for p in problems)
            raise RuntimeError(
                f"Configuración insegura para ENVIRONMENT='{self.environment}':\n{detail}"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
