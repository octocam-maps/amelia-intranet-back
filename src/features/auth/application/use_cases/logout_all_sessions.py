"""
Caso de uso: "cerrar sesión en todos los dispositivos" — revoca TODAS las
sesiones activas del usuario (todos los refresh tokens vivos), no solo la
actual. Pensado para incidentes RGPD / dispositivo perdido o robado.
"""

from ...domain.ports import ISessionRepository


class LogoutAllSessionsUseCase:
    def __init__(self, session_repository: ISessionRepository):
        self._session_repository = session_repository

    async def execute(self, user_id: str) -> int:
        """Devuelve cuántas sesiones se revocaron."""
        return await self._session_repository.revoke_all_sessions_for_user(user_id)
