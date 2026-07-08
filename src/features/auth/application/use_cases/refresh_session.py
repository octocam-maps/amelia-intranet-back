"""Caso de uso: renovar el access token a partir del refresh token (cookie HttpOnly)."""

from src.shared.errors.base import InvalidTokenError, TokenNotFoundError
from src.shared.jwt.domain.jwt_service import IJWTService

from ...domain.errors import UserSuspendedError
from ...domain.ports import IUserRepository
from ..results import RefreshResult


class RefreshSessionUseCase:
    def __init__(self, user_repository: IUserRepository, jwt_service: IJWTService):
        self._user_repository = user_repository
        self._jwt_service = jwt_service

    async def execute(self, refresh_token: str | None) -> RefreshResult:
        if not refresh_token:
            raise TokenNotFoundError("No refresh token provided.")

        payload = self._jwt_service.verify_token(refresh_token)
        if payload.get("type") != "refresh":
            raise InvalidTokenError("Token provided is not a refresh token.")

        user = await self._user_repository.find_by_id(payload["sub"])
        if user is None:
            raise InvalidTokenError("User no longer exists.")
        if user.status == "suspended":
            raise UserSuspendedError("Tu cuenta está suspendida.")

        access_token = self._jwt_service.create_access_token(
            {
                "sub": user.id,
                "email": user.email,
                "role": user.role_code,
                "entity_id": user.entity_id,
                "is_external": user.is_external,
            }
        )
        new_refresh_token = self._jwt_service.create_refresh_token({"sub": user.id})

        return RefreshResult(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=self._jwt_service.access_token_expire_minutes * 60,
        )
