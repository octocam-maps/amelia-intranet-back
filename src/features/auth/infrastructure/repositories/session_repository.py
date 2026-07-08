"""
Adaptador asyncpg del puerto `ISessionRepository`. SQL crudo sobre
`auth_sessions` (migración 008 + `family_id` de la 009) — única fuente de
verdad de revocación server-side de refresh tokens.
"""

from datetime import datetime
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import SessionRecord
from ...domain.ports import ISessionRepository


class PostgresSessionRepository(ISessionRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def create_session(
        self,
        *,
        user_id: str,
        jti: str,
        family_id: str,
        expires_at: datetime,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO auth_sessions (user_id, jti, family_id, expires_at, user_agent, ip_address)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            user_id,
            jti,
            family_id,
            expires_at,
            user_agent,
            ip_address,
        )

    async def find_session(self, jti: str) -> Optional[SessionRecord]:
        row = await self._db.fetchrow(
            "SELECT id, user_id, jti, family_id, revoked_at FROM auth_sessions WHERE jti = $1",
            jti,
        )
        if not row:
            return None
        return SessionRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            jti=row["jti"],
            family_id=str(row["family_id"]),
            is_revoked=row["revoked_at"] is not None,
        )

    async def revoke_session(self, jti: str) -> None:
        await self._db.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE jti = $1 AND revoked_at IS NULL
            """,
            jti,
        )

    async def revoke_family(self, family_id: str) -> int:
        result = await self._db.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE family_id = $1 AND revoked_at IS NULL
            """,
            family_id,
        )
        return self._parse_affected_rows(result)

    async def revoke_all_sessions_for_user(self, user_id: str) -> int:
        result = await self._db.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND revoked_at IS NULL
            """,
            user_id,
        )
        return self._parse_affected_rows(result)

    @staticmethod
    def _parse_affected_rows(execute_result: str) -> int:
        # asyncpg `execute` devuelve un status tipo "UPDATE 3".
        try:
            return int(execute_result.split()[-1])
        except (ValueError, IndexError):
            return 0
