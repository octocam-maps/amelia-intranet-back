"""
Caso de uso: renovar el access token a partir del refresh token (cookie
HttpOnly). Valida no solo la firma/expiración del JWT sino que su `jti`
siga activo en `auth_sessions` — así un logout o una revocación server-side
invalida el refresh token de inmediato, sin esperar a que expire.

Rota la sesión en cada refresh: revoca el `jti` viejo y persiste uno nuevo.
"""

import uuid

from src.shared.errors.base import InvalidTokenError, TokenNotFoundError
from src.shared.jwt.domain.jwt_service import IJWTService

from ...domain.errors import UserSuspendedError
from ...domain.ports import ISessionRepository, IUserRepository
from ..results import RefreshResult


class RefreshSessionUseCase:
    def __init__(
        self,
        user_repository: IUserRepository,
        session_repository: ISessionRepository,
        jwt_service: IJWTService,
    ):
        self._user_repository = user_repository
        self._session_repository = session_repository
        self._jwt_service = jwt_service

    async def execute(
        self,
        refresh_token: str | None,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> RefreshResult:
        if not refresh_token:
            raise TokenNotFoundError("No refresh token provided.")

        payload = self._jwt_service.verify_token(refresh_token)
        if payload.get("type") != "refresh":
            raise InvalidTokenError("Token provided is not a refresh token.")

        jti = payload.get("jti")
        if not jti or not await self._session_repository.is_session_active(jti):
            raise InvalidTokenError("Session has been revoked or no longer exists.")

        user = await self._user_repository.find_by_id(payload["sub"])
        if user is None:
            raise InvalidTokenError("User no longer exists.")
        if user.status == "suspended":
            raise UserSuspendedError("Tu cuenta está suspendida.")

        # Rotación: el jti viejo deja de servir en cuanto se usa una vez.
        await self._session_repository.revoke_session(jti)

        access_token = self._jwt_service.create_access_token(
            {
                "sub": user.id,
                "email": user.email,
                "role": user.role_code,
                "entity_id": user.entity_id,
                "is_external": user.is_external,
            }
        )
        new_jti = str(uuid.uuid4())
        new_refresh_token = self._jwt_service.create_refresh_token({"sub": user.id, "jti": new_jti})

        await self._session_repository.create_session(
            user_id=user.id,
            jti=new_jti,
            expires_at=self._jwt_service.get_refresh_token_expires_at(),
            user_agent=user_agent,
            ip_address=ip_address,
        )

        return RefreshResult(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=self._jwt_service.access_token_expire_minutes * 60,
        )
