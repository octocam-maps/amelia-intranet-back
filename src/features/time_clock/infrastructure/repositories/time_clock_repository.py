"""
Adaptador asyncpg del puerto `ITimeClockRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `time_clock_entries`.
"""

from datetime import date, datetime, timezone
from typing import Optional

import asyncpg

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import TimeClockBreak, TimeClockEntry
from ...domain.errors import TimeClockOverlapError
from ...domain.ports import ITimeClockRepository

_ENTRY_SELECT = """
    SELECT id, user_id, work_date, clock_in, clock_out, source, created_at, updated_at
    FROM time_clock_entries
"""

_BREAK_SELECT = "SELECT id, entry_id, break_start, break_end FROM time_clock_breaks"


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


def _row_to_break(row) -> TimeClockBreak:
    return TimeClockBreak(
        id=str(row["id"]),
        entry_id=str(row["entry_id"]),
        break_start=row["break_start"],
        break_end=row["break_end"],
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

    # --- Fichaje en vivo ---

    async def find_open_entry_for_user(self, user_id: str) -> Optional[TimeClockEntry]:
        row = await self._db.fetchrow(
            f"{_ENTRY_SELECT} WHERE user_id = $1 AND clock_out IS NULL ORDER BY clock_in DESC LIMIT 1",
            user_id,
        )
        return _row_to_entry(row) if row else None

    async def find_open_break_for_entry(self, entry_id: str) -> Optional[TimeClockBreak]:
        row = await self._db.fetchrow(
            f"{_BREAK_SELECT} WHERE entry_id = $1 AND break_end IS NULL LIMIT 1", entry_id
        )
        return _row_to_break(row) if row else None

    async def create_break(self, entry_id: str, break_start: datetime) -> TimeClockBreak:
        row = await self._db.fetchrow(
            """
            INSERT INTO time_clock_breaks (entry_id, break_start)
            VALUES ($1, $2)
            RETURNING id, entry_id, break_start, break_end
            """,
            entry_id,
            break_start,
        )
        return _row_to_break(row)

    async def close_break(self, break_id: str, break_end: datetime) -> TimeClockBreak:
        row = await self._db.fetchrow(
            """
            UPDATE time_clock_breaks SET break_end = $2
            WHERE id = $1
            RETURNING id, entry_id, break_start, break_end
            """,
            break_id,
            break_end,
        )
        return _row_to_break(row)

    async def get_week_worked_seconds(
        self, user_id: str, week_start: date, week_end: date
    ) -> float:
        # Resta las pausas del tiempo bruto del tramo — el tramo/pausa
        # abierto cuenta hasta AHORA (COALESCE(..., NOW())), así que el
        # contador "Esta semana" avanza en vivo sin que el frontend tenga
        # que re-sumarlo.
        rows = await self._db.fetch(
            """
            SELECT
                e.clock_in,
                e.clock_out,
                COALESCE(
                    SUM(EXTRACT(EPOCH FROM (COALESCE(b.break_end, NOW()) - b.break_start))),
                    0
                ) AS break_seconds
            FROM time_clock_entries e
            LEFT JOIN time_clock_breaks b ON b.entry_id = e.id
            WHERE e.user_id = $1 AND e.work_date BETWEEN $2 AND $3
            GROUP BY e.id, e.clock_in, e.clock_out
            """,
            user_id,
            week_start,
            week_end,
        )
        now = datetime.now(timezone.utc)
        total_seconds = 0.0
        for row in rows:
            gross = ((row["clock_out"] or now) - row["clock_in"]).total_seconds()
            total_seconds += max(gross - float(row["break_seconds"]), 0.0)
        return total_seconds
