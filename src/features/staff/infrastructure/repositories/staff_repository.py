"""
Adaptador asyncpg del puerto `IStaffRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `users`, `roles`,
`entities`, `departments` y (para el entitlement de vacaciones)
`absence_types`/`absence_balances`.
"""

from datetime import date
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import StaffMember
from ...domain.ports import IStaffRepository

_STAFF_SELECT = """
    SELECT
        u.id, u.full_name, u.email, u.avatar_url, u.job_title, u.status, u.hire_date, u.created_at,
        u.department_id, d.name AS department_name,
        u.entity_id, e.code AS entity_code,
        u.role_id, r.code AS role_code,
        ab.entitled_days AS vacation_days_per_year
    FROM users u
    JOIN roles r ON r.id = u.role_id
    LEFT JOIN entities e ON e.id = u.entity_id
    LEFT JOIN departments d ON d.id = u.department_id
    -- El entitlement de vacaciones vive en `absence_balances` (Fase 3), no
    -- en `users` — se toma el saldo del año en curso del tipo `vacaciones`.
    LEFT JOIN absence_types abt ON abt.code = 'vacaciones'
    LEFT JOIN absence_balances ab
        ON ab.user_id = u.id AND ab.absence_type_id = abt.id
        AND ab.year = EXTRACT(YEAR FROM CURRENT_DATE)::int
    WHERE u.deleted_at IS NULL
"""

# Upsert del entitlement anual — mismo patrón de "no-op upsert" que
# `absence_repository.get_or_create_balance`, pero aquí SÍ sobreescribe
# `entitled_days`: es el admin fijando explícitamente el valor, no un
# valor por defecto que solo se rellena la primera vez.
_UPSERT_VACATION_BALANCE = """
    INSERT INTO absence_balances (user_id, absence_type_id, year, entitled_days)
    SELECT $1, id, EXTRACT(YEAR FROM CURRENT_DATE)::int, $2
    FROM absence_types WHERE code = 'vacaciones'
    ON CONFLICT (user_id, absence_type_id, year)
    DO UPDATE SET entitled_days = EXCLUDED.entitled_days, updated_at = CURRENT_TIMESTAMP
"""


def _row_to_member(row) -> StaffMember:
    vacation_days = row["vacation_days_per_year"]
    return StaffMember(
        id=str(row["id"]),
        full_name=row["full_name"],
        email=row["email"],
        avatar_url=row["avatar_url"],
        job_title=row["job_title"],
        department_id=str(row["department_id"]) if row["department_id"] else None,
        department_name=row["department_name"],
        entity_id=str(row["entity_id"]) if row["entity_id"] else None,
        entity_code=row["entity_code"],
        role_id=str(row["role_id"]),
        role_code=row["role_code"],
        status=row["status"],
        hire_date=row["hire_date"],
        vacation_days_per_year=float(vacation_days) if vacation_days is not None else None,
        created_at=row["created_at"],
    )


class PostgresStaffRepository(IStaffRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    def _filtered_query(self, *, entity_code: Optional[str], search: Optional[str]):
        query = _STAFF_SELECT
        params: list = []
        if entity_code:
            params.append(entity_code)
            query += f" AND e.code = ${len(params)}"
        if search:
            params.append(f"%{search}%")
            query += f" AND u.full_name ILIKE ${len(params)}"
        return query, params

    async def list_staff(
        self,
        *,
        entity_code: Optional[str],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> list[StaffMember]:
        query, params = self._filtered_query(entity_code=entity_code, search=search)
        params.extend([page_size, (page - 1) * page_size])
        query += f" ORDER BY u.full_name LIMIT ${len(params) - 1} OFFSET ${len(params)}"
        rows = await self._db.fetch(query, *params)
        return [_row_to_member(row) for row in rows]

    async def count_staff(self, *, entity_code: Optional[str], search: Optional[str]) -> int:
        filter_sql = ""
        params: list = []
        if entity_code:
            params.append(entity_code)
            filter_sql += f" AND e.code = ${len(params)}"
        if search:
            params.append(f"%{search}%")
            filter_sql += f" AND u.full_name ILIKE ${len(params)}"
        query = f"""
            SELECT COUNT(*) FROM users u
            LEFT JOIN entities e ON e.id = u.entity_id
            WHERE u.deleted_at IS NULL {filter_sql}
        """
        return await self._db.fetchval(query, *params)

    async def find_by_id(self, user_id: str) -> Optional[StaffMember]:
        row = await self._db.fetchrow(f"{_STAFF_SELECT} AND u.id = $1", user_id)
        return _row_to_member(row) if row else None

    async def find_by_email(self, email: str) -> Optional[StaffMember]:
        row = await self._db.fetchrow(f"{_STAFF_SELECT} AND u.email = $1", email)
        return _row_to_member(row) if row else None

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]:
        row = await self._db.fetchval("SELECT id FROM entities WHERE code = $1", entity_code)
        return str(row) if row else None

    async def resolve_role_id(self, role_code: str) -> Optional[str]:
        row = await self._db.fetchval("SELECT id FROM roles WHERE code = $1", role_code)
        return str(row) if row else None

    async def get_or_create_department_id(self, *, entity_id: str, department_name: str) -> str:
        row = await self._db.fetchrow(
            """
            INSERT INTO departments (entity_id, name)
            VALUES ($1, $2)
            ON CONFLICT (entity_id, name) DO UPDATE SET updated_at = departments.updated_at
            RETURNING id
            """,
            entity_id,
            department_name,
        )
        return str(row["id"])

    async def create_staff_member(
        self,
        *,
        full_name: str,
        email: str,
        job_title: Optional[str],
        department_id: Optional[str],
        entity_id: str,
        role_id: str,
        is_external: bool,
        hire_date: Optional[date],
        vacation_days_per_year: Optional[float],
    ) -> StaffMember:
        async with self._db.acquire() as connection:
            async with connection.transaction():
                user_id = await connection.fetchval(
                    """
                    INSERT INTO users (
                        full_name, email, job_title, department_id,
                        entity_id, role_id, is_external, hire_date, status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'invited')
                    RETURNING id
                    """,
                    full_name,
                    email,
                    job_title,
                    department_id,
                    entity_id,
                    role_id,
                    is_external,
                    hire_date,
                )
                if vacation_days_per_year is not None:
                    await connection.execute(
                        _UPSERT_VACATION_BALANCE, user_id, vacation_days_per_year
                    )

        member = await self.find_by_id(str(user_id))
        assert member is not None
        return member

    async def update_staff_member(
        self,
        user_id: str,
        *,
        job_title: Optional[str],
        department_id: Optional[str],
        entity_id: Optional[str],
        role_id: Optional[str],
        is_external: Optional[bool],
        vacation_days_per_year: Optional[float],
        status: Optional[str],
    ) -> Optional[StaffMember]:
        async with self._db.acquire() as connection:
            async with connection.transaction():
                # COALESCE: cada parámetro en NULL deja la columna como
                # estaba — semántica PATCH (actualización parcial).
                found = await connection.fetchval(
                    """
                    UPDATE users
                    SET job_title = COALESCE($2, job_title),
                        department_id = COALESCE($3, department_id),
                        entity_id = COALESCE($4, entity_id),
                        role_id = COALESCE($5, role_id),
                        is_external = COALESCE($6, is_external),
                        status = COALESCE($7, status),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND deleted_at IS NULL
                    RETURNING id
                    """,
                    user_id,
                    job_title,
                    department_id,
                    entity_id,
                    role_id,
                    is_external,
                    status,
                )
                if found is None:
                    return None
                if vacation_days_per_year is not None:
                    await connection.execute(
                        _UPSERT_VACATION_BALANCE, user_id, vacation_days_per_year
                    )

        return await self.find_by_id(user_id)
