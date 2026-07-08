"""
Configuración centralizada leída de variables de entorno.
Un único punto de lectura para evitar `os.getenv` disperso por el código.
"""

import os
from functools import lru_cache


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings:
    def __init__(self) -> None:
        self.environment = os.getenv("ENVIRONMENT", "dev")
        self.swagger_enabled = _is_truthy(os.getenv("SWAGGER_ENABLED", "true"))

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
        self.refresh_token_cookie_secure = _is_truthy(
            os.getenv("REFRESH_TOKEN_COOKIE_SECURE", "false")
        )

        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.google_workspace_hosted_domain = os.getenv(
            "GOOGLE_WORKSPACE_HOSTED_DOMAIN", "ameliahub.com"
        )

        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")
        self.sendgrid_from_email = os.getenv("SENDGRID_FROM_EMAIL", "no-reply@ameliahub.com")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")


@lru_cache
def get_settings() -> Settings:
    return Settings()
