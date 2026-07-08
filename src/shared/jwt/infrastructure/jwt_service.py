"""
JWT interno de la intranet. NO tiene relación con el id_token de Google: se
emite DESPUÉS de verificar la identidad Google, y es el único credential que
el frontend usa para hablar con esta API (Authorization: Bearer <access>).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import ExpiredSignatureError, JWTError, jwt

from src.shared.config import get_settings
from src.shared.errors.base import InvalidTokenError, TokenExpiredError


class JWTService:
    """Servicio de JWT interno (creación/verificación de access y refresh)."""

    _instance: Optional["JWTService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        settings = get_settings()
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.access_token_expire_minutes = settings.jwt_access_token_expire_minutes
        self.refresh_token_expire_days = settings.jwt_refresh_token_expire_days
        self._initialized = True

    def create_access_token(
        self, data: dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=self.access_token_expire_minutes)
        )
        to_encode.update(
            {"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"}
        )
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(
        self, data: dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(days=self.refresh_token_expire_days)
        )
        to_encode.update(
            {"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"}
        )
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except ExpiredSignatureError:
            raise TokenExpiredError("Access token has expired")
        except JWTError:
            raise InvalidTokenError("Invalid token")

    def get_refresh_token_expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)


_jwt_service_instance: Optional[JWTService] = None


def get_jwt_service() -> JWTService:
    """Devuelve la instancia singleton de JWTService."""
    global _jwt_service_instance
    if _jwt_service_instance is None:
        _jwt_service_instance = JWTService()
    return _jwt_service_instance
