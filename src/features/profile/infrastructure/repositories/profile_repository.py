"""
Adaptador asyncpg del puerto `IProfileRepository`. SQL crudo — sin ORM.
Mismo patrón de JOINs que `features/staff/infrastructure/repositories/
staff_repository.py`, pero resolviendo NOMBRES (no códigos) de entidad y
departamento, y el nombre del manager vía self-join de `users`.
"""

from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import UserProfile
from ...domain.ports import IProfileRepository

_PROFILE_SELECT = """
    SELECT
        u.id, u.email, u.full_name, u.avatar_url, u.job_title,
        u.hire_date, u.is_external,
        r.code AS role_code,
        e.name AS entity_name,
        d.name AS department_name,
        m.full_name AS manager_name
    FROM users u
    JOIN roles r ON r.id = u.role_id
    LEFT JOIN entities e ON e.id = u.entity_id
    LEFT JOIN departments d ON d.id = u.department_id
    -- `m.deleted_at IS NULL` en el propio JOIN (no en el WHERE, que ya
    -- filtra `u.deleted_at`): sin esto, un manager dado de baja seguía
    -- apareciendo como `manager_name` del perfil de su antiguo reporte
    -- (bug real, auditoría QA).
    LEFT JOIN users m ON m.id = u.manager_id AND m.deleted_at IS NULL
    WHERE u.id = $1 AND u.deleted_at IS NULL
"""


def _row_to_profile(row) -> UserProfile:
    return UserProfile(
        id=str(row["id"]),
        email=row["email"],
        full_name=row["full_name"],
        avatar_url=row["avatar_url"],
        role_code=row["role_code"],
        job_title=row["job_title"],
        hire_date=row["hire_date"],
        entity_name=row["entity_name"],
        department_name=row["department_name"],
        manager_name=row["manager_name"],
        is_external=row["is_external"],
    )


class PostgresProfileRepository(IProfileRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def find_profile_by_user_id(self, user_id: str) -> Optional[UserProfile]:
        row = await self._db.fetchrow(_PROFILE_SELECT, user_id)
        return _row_to_profile(row) if row else None
