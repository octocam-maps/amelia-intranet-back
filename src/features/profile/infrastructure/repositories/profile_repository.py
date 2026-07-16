"""
Adaptador asyncpg del puerto `IProfileRepository`. SQL crudo — sin ORM.
Mismo patrón de JOINs que `features/staff/infrastructure/repositories/
staff_repository.py`, pero resolviendo NOMBRES (no códigos) de entidad y
departamento, y el nombre del manager vía self-join de `users`.

Lote 2: `phone`/`city` viven en `user_profiles` (022_user_profiles_city.sql),
no en `users` — se traen con LEFT JOIN porque, a diferencia de `users`, no
existe fila en `user_profiles` para todo usuario (ningún caso de uso escribía
ahí todavía; el borrador del paso 5 del onboarding se guarda aparte en
`onboarding_progress.data`, ver `complete_profile.py`). Este feature es el
PRIMER escritor real de `user_profiles` — por eso `update_profile_contact`
hace UPSERT, no UPDATE (la fila puede no existir aún).
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
        m.full_name AS manager_name,
        p.phone AS phone,
        p.city AS city
    FROM users u
    JOIN roles r ON r.id = u.role_id
    LEFT JOIN entities e ON e.id = u.entity_id
    LEFT JOIN departments d ON d.id = u.department_id
    -- `m.deleted_at IS NULL` en el propio JOIN (no en el WHERE, que ya
    -- filtra `u.deleted_at`): sin esto, un manager dado de baja seguía
    -- apareciendo como `manager_name` del perfil de su antiguo reporte
    -- (bug real, auditoría QA).
    LEFT JOIN users m ON m.id = u.manager_id AND m.deleted_at IS NULL
    LEFT JOIN user_profiles p ON p.user_id = u.id
    WHERE u.id = $1 AND u.deleted_at IS NULL
"""

# UPSERT en vez de UPDATE: `user_profiles` puede no tener fila para este
# usuario todavía (ver docstring del módulo). COALESCE en la rama de
# conflicto: cada parámetro en NULL deja la columna como estaba — semántica
# PATCH (mismo criterio que `staff_repository._UPSERT_VACATION_BALANCE` /
# `update_staff_member`). En la rama de INSERT no hace falta COALESCE: es la
# primera fila, no hay nada previo que preservar.
_UPSERT_PROFILE_CONTACT = """
    INSERT INTO user_profiles (user_id, phone, city)
    VALUES ($1, $2, $3)
    ON CONFLICT (user_id) DO UPDATE
    SET phone = COALESCE($2, user_profiles.phone),
        city = COALESCE($3, user_profiles.city),
        updated_at = CURRENT_TIMESTAMP
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
        phone=row["phone"],
        city=row["city"],
    )


class PostgresProfileRepository(IProfileRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def find_profile_by_user_id(self, user_id: str) -> Optional[UserProfile]:
        row = await self._db.fetchrow(_PROFILE_SELECT, user_id)
        return _row_to_profile(row) if row else None

    async def update_profile_contact(
        self, user_id: str, *, phone: Optional[str], city: Optional[str]
    ) -> Optional[UserProfile]:
        # Confirma que el usuario existe (no borrado) ANTES de tocar
        # `user_profiles` — evita insertar una fila huérfana de contacto
        # para un `user_id` inexistente/dado de baja (la FK con
        # ON DELETE CASCADE no protege de esto: un id simplemente inventado
        # rompería por violación de FK, un 500 feo en vez de un 404 claro).
        existing = await self.find_profile_by_user_id(user_id)
        if existing is None:
            return None

        await self._db.execute(_UPSERT_PROFILE_CONTACT, user_id, phone, city)
        return await self.find_profile_by_user_id(user_id)
