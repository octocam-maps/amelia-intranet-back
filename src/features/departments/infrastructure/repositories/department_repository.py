"""
Adaptador asyncpg del puerto `IDepartmentRepository`. SQL crudo — sin ORM.
`LEFT JOIN entities` sigue el mismo patrón que
`staff/infrastructure/repositories/staff_repository.py` (columna
`entity_code` para mostrar la entidad junto al nombre del departamento).
"""

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import Department
from ...domain.ports import IDepartmentRepository

# Filtra por la entidad del usuario, con FALLBACK a todos si no tiene ninguna.
#
# El `OR` del WHERE es lo que implementa ese fallback en una sola consulta: si la
# subconsulta de la entidad del usuario da NULL, la primera condición vale NULL
# (no TRUE) y es la segunda la que deja pasar todas las filas. Se resuelve en SQL
# y no con un `if` en Python para no hacer dos viajes a la base ni mantener dos
# caminos que puedan divergir.
#
# `ORDER BY e.code, d.name` agrupa por sociedad. Solo se nota en el caso del
# usuario sin entidad —el único que sigue viendo las 20 filas—, que es justo
# cuando más falta hace.
_SELECT_DEPARTMENTS_FOR_USER = """
    SELECT d.id, d.name, d.entity_id, e.code AS entity_code
    FROM departments d
    LEFT JOIN entities e ON e.id = d.entity_id
    WHERE d.entity_id = (SELECT entity_id FROM users WHERE id = $1)
       OR (SELECT entity_id FROM users WHERE id = $1) IS NULL
    ORDER BY e.code, d.name
"""

# Mismo criterio de fallback que arriba, y por el mismo motivo: sin el `OR`, un
# usuario sin entidad no podría guardar NINGÚN departamento y se quedaría sin
# poder completar el paso 4.
_DEPARTMENT_BELONGS_TO_USER_ENTITY = """
    SELECT 1
    FROM departments d
    WHERE d.id = $1
      AND (
          d.entity_id = (SELECT entity_id FROM users WHERE id = $2)
          OR (SELECT entity_id FROM users WHERE id = $2) IS NULL
      )
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

    async def list_departments_for_user(self, user_id: str) -> list[Department]:
        rows = await self._db.fetch(_SELECT_DEPARTMENTS_FOR_USER, user_id)
        return [_row_to_department(row) for row in rows]

    async def department_belongs_to_user_entity(
        self, department_id: str, user_id: str
    ) -> bool:
        row = await self._db.fetchrow(
            _DEPARTMENT_BELONGS_TO_USER_ENTITY, department_id, user_id
        )
        return row is not None
