"""
Adaptador asyncpg del puerto `ITimeClockRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `time_clock_entries`.
"""

from datetime import date, datetime
from typing import Optional

import asyncpg

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import TimeClockEntry
from ...domain.errors import TimeClockOverlapError
from ...domain.ports import ITimeClockRepository

_ENTRY_SELECT = """
    SELECT id, user_id, work_date, clock_in, clock_out, source, created_at, updated_at
    FROM time_clock_entries
"""


def _row_to_entry(row) -> TimeClockEntry:
    return TimeClockEntry(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        work_date=row["work_date"],
        clock_in=row["clock_in"],
        clock_out=row["clock_out"],
        source=row["source"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresTimeClockRepository(ITimeClockRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def create_entry(
        self,
        *,
        user_id: str,
        work_date: date,
        clock_in: datetime,
        clock_out: Optional[datetime],
        source: str,
    ) -> TimeClockEntry:
        # RACE-3: `find_overlapping_entry` ya se comprueba en el use case,
        # pero eso es un check-then-act — el constraint EXCLUDE de la
        # migración 012 es la fuente de verdad real bajo concurrencia. Si
        # dos tramos concurrentes del mismo usuario/día se solapan, Postgres
        # rechaza el segundo INSERT con ExclusionViolationError.
        try:
            row = await self._db.fetchrow(
                """
                INSERT INTO time_clock_entries (user_id, work_date, clock_in, clock_out, source)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, user_id, work_date, clock_in, clock_out, source, created_at, updated_at
                """,
                user_id,
                work_date,
                clock_in,
                clock_out,
                source,
            )
        except asyncpg.exceptions.ExclusionViolationError as e:
            raise TimeClockOverlapError(
                "Ese tramo se solapa con otro fichaje ya registrado ese día."
            ) from e
        return _row_to_entry(row)

    async def find_entry_by_id(self, entry_id: str) -> Optional[TimeClockEntry]:
        row = await self._db.fetchrow(f"{_ENTRY_SELECT} WHERE id = $1", entry_id)
        return _row_to_entry(row) if row else None

    async def list_entries_for_user(
        self, user_id: str, *, date_from: date, date_to: date
    ) -> list[TimeClockEntry]:
        rows = await self._db.fetch(
            f"""
            {_ENTRY_SELECT}
            WHERE user_id = $1 AND work_date BETWEEN $2 AND $3
            ORDER BY work_date DESC, clock_in DESC
            """,
            user_id,
            date_from,
            date_to,
        )
        return [_row_to_entry(row) for row in rows]

    async def list_entries_for_all(
        self, *, date_from: date, date_to: date
    ) -> list[TimeClockEntry]:
        rows = await self._db.fetch(
            f"""
            {_ENTRY_SELECT}
            WHERE work_date BETWEEN $1 AND $2
            ORDER BY work_date DESC, clock_in DESC
            """,
            date_from,
            date_to,
        )
        return [_row_to_entry(row) for row in rows]

    async def find_overlapping_entry(
        self,
        user_id: str,
        work_date: date,
        clock_in: datetime,
        clock_out: Optional[datetime],
        *,
        exclude_entry_id: Optional[str] = None,
    ) -> Optional[TimeClockEntry]:
        # Un tramo abierto (`clock_out` NULL) se trata como si terminara "ahora"
        # a efectos de solape: se compara contra COALESCE(clock_out, 'infinity').
        row = await self._db.fetchrow(
            f"""
            {_ENTRY_SELECT}
            WHERE user_id = $1
              AND work_date = $2
              AND ($5::uuid IS NULL OR id != $5)
              AND clock_in < COALESCE($4, 'infinity'::timestamptz)
              AND COALESCE(clock_out, 'infinity'::timestamptz) > $3
            LIMIT 1
            """,
            user_id,
            work_date,
            clock_in,
            clock_out,
            exclude_entry_id,
        )
        return _row_to_entry(row) if row else None

    async def update_entry(
        self, entry_id: str, *, clock_in: datetime, clock_out: Optional[datetime]
    ) -> TimeClockEntry:
        try:
            row = await self._db.fetchrow(
                """
                UPDATE time_clock_entries
                SET clock_in = $2, clock_out = $3, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                RETURNING id, user_id, work_date, clock_in, clock_out, source, created_at, updated_at
                """,
                entry_id,
                clock_in,
                clock_out,
            )
        except asyncpg.exceptions.ExclusionViolationError as e:
            raise TimeClockOverlapError(
                "Ese tramo se solapa con otro fichaje ya registrado ese día."
            ) from e
        return _row_to_entry(row)

    async def delete_entry(self, entry_id: str) -> None:
        await self._db.execute("DELETE FROM time_clock_entries WHERE id = $1", entry_id)
