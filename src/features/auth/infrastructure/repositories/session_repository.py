"""
Adaptador asyncpg del puerto `ISessionRepository`. SQL crudo sobre
`auth_sessions` (migración 008) — única fuente de verdad de revocación
server-side de refresh tokens.
"""

from datetime import datetime
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.ports import ISessionRepository


class PostgresSessionRepository(ISessionRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def create_session(
        self,
        *,
        user_id: str,
        jti: str,
        expires_at: datetime,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO auth_sessions (user_id, jti, expires_at, user_agent, ip_address)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id,
            jti,
            expires_at,
            user_agent,
            ip_address,
        )

    async def is_session_active(self, jti: str) -> bool:
        row = await self._db.fetchrow(
            "SELECT 1 FROM auth_sessions WHERE jti = $1 AND revoked_at IS NULL", jti
        )
        return row is not None

    async def revoke_session(self, jti: str) -> None:
        await self._db.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE jti = $1 AND revoked_at IS NULL
            """,
            jti,
        )

    async def revoke_all_sessions_for_user(self, user_id: str) -> int:
        result = await self._db.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND revoked_at IS NULL
            """,
            user_id,
        )
        # asyncpg `execute` devuelve un status tipo "UPDATE 3".
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
