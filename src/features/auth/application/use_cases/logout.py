"""
Caso de uso: logout. Revoca server-side TODA la familia de sesiones del
refresh token actual (no solo su `jti` puntual) — así, aunque el navegador
tuviera de milagro un descendiente ya rotado en vuelo, también queda
invalidado. Además el router borra la cookie. Si el refresh token ya no es
válido/decodificable (expirado, ausente), no falla — el objetivo de logout
es que el usuario quede fuera, no exigirle un token perfecto.
"""

from src.shared.jwt.domain.jwt_service import IJWTService
from src.shared.logger import get_logger

from ...domain.ports import ISessionRepository

logger = get_logger("auth.logout")


class LogoutUseCase:
    def __init__(self, session_repository: ISessionRepository, jwt_service: IJWTService):
        self._session_repository = session_repository
        self._jwt_service = jwt_service

    async def execute(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return

        try:
            payload = self._jwt_service.verify_token(refresh_token)
        except Exception as e:
            # Igual que `AuthMiddleware`: se loguea a nivel debug para poder
            # investigar (p.ej. un cliente mandando tokens corruptos de
            # forma sistemática) sin romper la garantía de que logout NUNCA
            # falla — antes este fallo quedaba completamente en silencio.
            logger.debug(
                "Logout with an unverifiable refresh token",
                error_type=type(e).__name__,
            )
            return

        jti = payload.get("jti")
        if not jti:
            return

        session = await self._session_repository.find_session(jti)
        if session is not None:
            await self._session_repository.revoke_family(session.family_id)
