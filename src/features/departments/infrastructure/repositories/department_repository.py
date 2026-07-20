"""
Adaptador asyncpg del puerto `IDepartmentRepository`. SQL crudo — sin ORM.
`LEFT JOIN entities` sigue el mismo patrón que
`staff/infrastructure/repositories/staff_repository.py` (columna
`entity_code` para mostrar la entidad junto al nombre del departamento).
"""

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import Department
from ...domain.ports import IDepartmentRepository

_SELECT_DEPARTMENTS = """
    SELECT d.id, d.name, d.entity_id, e.code AS entity_code
    FROM departments d
    LEFT JOIN entities e ON e.id = d.entity_id
    ORDER BY d.name
"""


def _row_to_department(row) -> Department:
    return Department(
        id=str(row["id"]),
        name=row["name"],
        entity_id=str(row["entity_id"]),
        entity_code=row["entity_code"],
    )


class PostgresDepartmentRepository(IDepartmentRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_departments(self) -> list[Department]:
        rows = await self._db.fetch(_SELECT_DEPARTMENTS)
        return [_row_to_department(row) for row in rows]
