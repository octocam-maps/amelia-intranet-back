"""
Adaptador asyncpg del puerto `IRoleRepository`. SQL crudo — sin ORM. Único
lugar del feature que conoce el esquema de `roles` (001_core_identity.sql).
"""

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import Role
from ...domain.ports import IRoleRepository


def _row_to_role(row) -> Role:
    return Role(id=str(row["id"]), code=row["code"], name=row["name"])


class PostgresRoleRepository(IRoleRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_roles(self) -> list[Role]:
        rows = await self._db.fetch("SELECT id, code, name FROM roles ORDER BY code")
        return [_row_to_role(row) for row in rows]
