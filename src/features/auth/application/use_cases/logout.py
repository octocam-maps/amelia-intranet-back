"""
Caso de uso: logout. Revoca server-side la sesión asociada al refresh token
actual (además de que el router borra la cookie). Si el refresh token ya no
es válido/decodificable (expirado, ausente), no falla — el objetivo de
logout es que el usuario quede fuera, no exigirle un token perfecto.
"""

from src.shared.jwt.domain.jwt_service import IJWTService

from ...domain.ports import ISessionRepository


class LogoutUseCase:
    def __init__(self, session_repository: ISessionRepository, jwt_service: IJWTService):
        self._session_repository = session_repository
        self._jwt_service = jwt_service

    async def execute(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return

        try:
            payload = self._jwt_service.verify_token(refresh_token)
        except Exception:
            return

        jti = payload.get("jti")
        if jti:
            await self._session_repository.revoke_session(jti)
