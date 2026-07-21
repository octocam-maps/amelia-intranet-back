"""
Dependencias FastAPI para autenticación y RBAC. Este es el único lugar que
decide si una request está autenticada y con qué rol — el navbar del
frontend es solo cosmético, la autorización real vive aquí (regla del
proyecto: "ocultar ≠ proteger").

`get_current_user`:
  1. Lee `request.state.current_user` si `AuthMiddleware` ya verificó el
     token (fast path, evita verificar dos veces).
  2. Si no, extrae el `Authorization: Bearer <token>` y lo verifica.
  3. AUTHN-2: además valida contra BD que el usuario siga activo (corte
     inmediato ante suspensión, ver `ensure_user_is_active`).

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

from src.shared.database import get_database_pool
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


async def ensure_user_is_active(user_id: str) -> None:
    """AUTHN-2 (pentest, severidad MEDIA): corte inmediato al suspender.

    `verify_token` (firma/exp/type) certifica que el JWT fue emitido por
    nosotros y no expiró, pero un access token es stateless: si un admin
    suspende a alguien (`PATCH /staff/{id}` con `is_active:false` ->
    `users.status = 'suspended'`), ese token seguía sirviendo hasta 15 min
    contra CUALQUIER endpoint (incluida la descarga de nóminas) porque el
    chequeo de `suspended` solo vivía en login/refresh, nunca acá.

    Decisión de producto: corte inmediato vía un SELECT por PK indexado en
    cada request (sub-ms para el volumen de la intranet), SIN cache/Redis.
    Esta función es el único punto a tocar si algún día hace falta cachear
    el resultado.
    """
    db_pool = get_database_pool()
    status = await db_pool.fetchval("SELECT status FROM users WHERE id = $1", user_id)
    if status != "active":
        logger.warning(
            "Rejected access token: user is not active",
            user_id=user_id,
            status=status,
        )
        raise InvalidTokenError("User account is not active")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security_bearer),
) -> dict:
    """Usuario autenticado actual (payload del JWT interno).

    AUTHN-1: un refresh token no debe servir como credential contra
    endpoints protegidos solo con esta dependencia (`/auth/me`,
    `/auth/logout`, `/auth/logout-all`) — `verify_token` valida firma/exp
    pero no el claim `type`, así que se valida acá, DESPUÉS de resolver el
    payload por cualquiera de los dos caminos: el fast-path cacheado por
    `AuthMiddleware` (que cachea cualquier token válido, incluido un
    refresh) y la verificación directa del header `Authorization`.
    """
    cached_user = getattr(request.state, "current_user", None)
    if cached_user is not None:
        payload = cached_user
    else:
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
        except (TokenExpiredError, InvalidTokenError):
            raise
        except Exception as e:
            logger.error(
                "Unexpected error verifying token",
                error_type=type(e).__name__,
                error=str(e),
            )
            raise InvalidCredentialsError("Could not validate credentials")

    if payload.get("type") != "access":
        logger.warning(
            "Rejected non-access token used as bearer credential",
            token_type=payload.get("type"),
            user_id=payload.get("sub"),
        )
        raise InvalidTokenError("Token type is not valid for this operation")

    # AUTHN-2: firma/exp/type ya validados arriba, pero eso no dice si el
    # usuario sigue activo AHORA — corte inmediato ante suspensión.
    await ensure_user_is_active(payload.get("sub"))

    return payload


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
