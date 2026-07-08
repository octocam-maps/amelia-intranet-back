"""
Dependencias FastAPI para autenticación y RBAC. Este es el único lugar que
decide si una request está autenticada y con qué rol — el navbar del
frontend es solo cosmético, la autorización real vive aquí (regla del
proyecto: "ocultar ≠ proteger").

`get_current_user`:
  1. Lee `request.state.current_user` si `AuthMiddleware` ya verificó el
     token (fast path, evita verificar dos veces).
  2. Si no, extrae el `Authorization: Bearer <token>` y lo verifica.

`require_role(*roles)`:
  Devuelve una dependencia que además exige que `current_user["role"]` esté
  en la lista de roles permitidos. Se usa así:

      @router.get("/admin/plantilla")
      async def list_staff(user: dict = Depends(require_role("administrador"))):
          ...

  Si el rol no es válido, responde 403 — nunca deja pasar por "no encontrar"
  el endpoint en el navbar del rol equivocado.
"""

from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.shared.errors.base import (
    AuthenticationRequiredError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
)
from src.shared.jwt import get_jwt_service
from src.shared.logger import get_logger

logger = get_logger("shared.auth.dependencies")

_security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security_bearer),
) -> dict:
    """Usuario autenticado actual (payload del JWT interno)."""
    cached_user = getattr(request.state, "current_user", None)
    if cached_user is not None:
        return cached_user

    if not credentials:
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationRequiredError("Authentication required")
        token = authorization.split(" ")[1]
    else:
        token = credentials.credentials

    jwt_service = get_jwt_service()
    try:
        payload = jwt_service.verify_token(token)
        request.state.current_user = payload
        return payload
    except (TokenExpiredError, InvalidTokenError):
        raise
    except Exception as e:
        logger.error(
            "Unexpected error verifying token",
            error_type=type(e).__name__,
            error=str(e),
        )
        raise InvalidCredentialsError("Could not validate credentials")


def require_role(*allowed_roles: str):
    """Fábrica de dependencia: exige que el usuario tenga uno de `allowed_roles`."""

    async def _dependency(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role")
        if role not in allowed_roles:
            logger.warning(
                "Access denied: role not allowed",
                role=role,
                allowed_roles=list(allowed_roles),
                user_id=user.get("sub"),
            )
            raise InsufficientPermissionsError(
                "You do not have permission to perform this action."
            )
        return user

    return _dependency
