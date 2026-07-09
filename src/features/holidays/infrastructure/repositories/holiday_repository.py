"""
Adaptador asyncpg del puerto `IHolidayRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `holidays`
(003_hr_core.sql + 017_holidays_updated_at.sql).
"""

from datetime import date
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import Holiday
from ...domain.ports import IHolidayRepository

_SELECT = """
    SELECT h.id, h.day, h.name, h.entity_id, e.code AS entity_code,
           h.created_at, h.updated_at
    FROM holidays h
    LEFT JOIN entities e ON e.id = h.entity_id
"""


def _row_to_holiday(row) -> Holiday:
    return Holiday(
        id=str(row["id"]),
        day=row["day"],
        name=row["name"],
        entity_id=str(row["entity_id"]) if row["entity_id"] else None,
        entity_code=row["entity_code"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresHolidayRepository(IHolidayRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_holidays(
        self, *, year: Optional[int], entity_code: Optional[str]
    ) -> list[Holiday]:
        query = f"{_SELECT} WHERE TRUE"
        params: list = []
        if year is not None:
            params.append(year)
            query += f" AND EXTRACT(YEAR FROM h.day) = ${len(params)}"
        if entity_code is not None:
            params.append(entity_code)
            query += f" AND (e.code = ${len(params)} OR h.entity_id IS NULL)"
        query += " ORDER BY h.day ASC"
        rows = await self._db.fetch(query, *params)
        return [_row_to_holiday(row) for row in rows]

    async def find_by_id(self, holiday_id: str) -> Optional[Holiday]:
        row = await self._db.fetchrow(f"{_SELECT} WHERE h.id = $1", holiday_id)
        return _row_to_holiday(row) if row else None

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]:
        row = await self._db.fetchval("SELECT id FROM entities WHERE code = $1", entity_code)
        return str(row) if row else None

    async def create_holiday(
        self, *, day: date, name: str, entity_id: Optional[str]
    ) -> Holiday:
        row = await self._db.fetchrow(
            """
            INSERT INTO holidays (day, name, entity_id)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            day,
            name,
            entity_id,
        )
        holiday = await self.find_by_id(str(row["id"]))
        assert holiday is not None
        return holiday

    async def update_holiday(
        self,
        holiday_id: str,
        *,
        day: Optional[date],
        name: Optional[str],
        entity_id: Optional[str],
        clear_entity: bool,
    ) -> Optional[Holiday]:
        found = await self._db.fetchval(
            """
            UPDATE holidays
            SET day = COALESCE($2, day),
                name = COALESCE($3, name),
                entity_id = CASE WHEN $4 THEN NULL ELSE COALESCE($5, entity_id) END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            RETURNING id
            """,
            holiday_id,
            day,
            name,
            clear_entity,
            entity_id,
        )
        if found is None:
            return None
        return await self.find_by_id(holiday_id)

    async def delete_holiday(self, holiday_id: str) -> bool:
        found = await self._db.fetchval(
            "DELETE FROM holidays WHERE id = $1 RETURNING id", holiday_id
        )
        return found is not None
