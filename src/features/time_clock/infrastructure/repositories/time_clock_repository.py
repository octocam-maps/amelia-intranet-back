"""
Adaptador asyncpg del puerto `ITimeClockRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `time_clock_entries`.
"""

from datetime import date, datetime, timezone
from typing import Optional

import asyncpg

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import TimeClockBreak, TimeClockEntry, TimeClockExportRow
from ...domain.errors import (
    TimeClockAlreadyClockedInError,
    TimeClockBreakAlreadyOpenError,
    TimeClockOverlapError,
)
from ...domain.ports import ITimeClockRepository

_ENTRY_SELECT = """
    SELECT id, user_id, work_date, clock_in, clock_out, source, created_at, updated_at
    FROM time_clock_entries
"""

_BREAK_SELECT = "SELECT id, entry_id, break_start, break_end FROM time_clock_breaks"

# Informe admin XLSX: junta el tramo con identidad/contacto de `users` +
# `user_profiles`. Solo plantilla INTERNA (`is_external = FALSE`) — el
# externo-invitado no tiene Control horario en la matriz de permisos, así
# que nunca debería aparecer aquí aunque algún día tuviera fichajes.
#
# El `ORDER BY` reparte `full_name` con la MISMA heurística que
# `infrastructure/xlsx_export.py::_split_full_name` (Nombre = primera
# palabra, Apellido = el resto) para que el orden de las filas del informe
# coincida con lo que el admin lee en las columnas Nombre/Apellido.
_EXPORT_SELECT = """
    SELECT
        u.id AS user_id,
        u.full_name,
        p.dni_nif,
        p.phone,
        e.work_date,
        e.clock_in,
        e.clock_out
    FROM time_clock_entries e
    JOIN users u ON u.id = e.user_id
    LEFT JOIN user_profiles p ON p.user_id = u.id
    WHERE e.work_date BETWEEN $1 AND $2
      AND u.deleted_at IS NULL
      AND u.is_external = FALSE
    ORDER BY
        CASE WHEN u.full_name LIKE '% %'
             THEN SUBSTRING(u.full_name FROM POSITION(' ' IN u.full_name) + 1)
             ELSE ''
        END,
        SPLIT_PART(u.full_name, ' ', 1),
        e.work_date DESC
"""

# Informe empleado XLSX: mismo join que `_EXPORT_SELECT`, acotado a
# `u.id = $1` (RGPD — cada trabajador exporta SOLO sus propios fichajes,
# nunca los de otro). No filtra por `is_external`: si algún día un
# externo-invitado tuviera fichajes, seguiría viendo únicamente los suyos.
_EXPORT_SELECT_FOR_USER = """
    SELECT
        u.id AS user_id,
        u.full_name,
        p.dni_nif,
        p.phone,
        e.work_date,
        e.clock_in,
        e.clock_out
    FROM time_clock_entries e
    JOIN users u ON u.id = e.user_id
    LEFT JOIN user_profiles p ON p.user_id = u.id
    WHERE u.id = $1
      AND e.work_date BETWEEN $2 AND $3
      AND u.deleted_at IS NULL
    ORDER BY e.work_date DESC
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


def _row_to_export_row(row) -> TimeClockExportRow:
    return TimeClockExportRow(
        user_id=str(row["user_id"]),
        full_name=row["full_name"],
        dni_nif=row["dni_nif"],
        phone=row["phone"],
        work_date=row["work_date"],
        clock_in=row["clock_in"],
        clock_out=row["clock_out"],
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
            if clock_out is None:
                # Rama de FICHAJE EN VIVO (botón play del dashboard): bajo
                # carrera, un segundo clock-in choca con el mismo EXCLUDE que
                # protege el alta manual de tramos, pero el mensaje correcto
                # aquí NO es "se solapa" — es "ya tienes un fichaje en
                # curso", el mismo que da el check-then-act del use case en
                # el camino feliz (bug real, auditoría QA: bajo carrera el
                # 2º clock-in mostraba el mensaje de solape en vez de este).
                raise TimeClockAlreadyClockedInError(
                    "Ya tienes un fichaje en curso — ficha salida antes de volver a entrar."
                ) from e
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

    async def list_export_rows_for_all(
        self, *, date_from: date, date_to: date
    ) -> list[TimeClockExportRow]:
        rows = await self._db.fetch(_EXPORT_SELECT, date_from, date_to)
        return [_row_to_export_row(row) for row in rows]

    async def list_export_rows_for_user(
        self, user_id: str, *, date_from: date, date_to: date
    ) -> list[TimeClockExportRow]:
        rows = await self._db.fetch(_EXPORT_SELECT_FOR_USER, user_id, date_from, date_to)
        return [_row_to_export_row(row) for row in rows]

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
        # `ORDER BY break_start DESC`: si por cualquier motivo hubiera más de una
        # pausa abierta, se recupera la más reciente de forma determinista (el
        # índice único parcial de la migración 021 impide que eso ocurra, pero
        # el orden explícito evita comportamiento no determinista igualmente).
        row = await self._db.fetchrow(
            f"{_BREAK_SELECT} WHERE entry_id = $1 AND break_end IS NULL "
            "ORDER BY break_start DESC LIMIT 1",
            entry_id,
        )
        return _row_to_break(row) if row else None

    async def create_break(self, entry_id: str, break_start: datetime) -> TimeClockBreak:
        try:
            row = await self._db.fetchrow(
                """
                INSERT INTO time_clock_breaks (entry_id, break_start)
                VALUES ($1, $2)
                RETURNING id, entry_id, break_start, break_end
                """,
                entry_id,
                break_start,
            )
        except asyncpg.UniqueViolationError as exc:
            # Backstop del índice único parcial (migración 021): dos "Pausa"
            # concurrentes sobre el mismo tramo — el check-then-act del use case
            # no basta bajo carrera; la BD garantiza una sola pausa abierta.
            raise TimeClockBreakAlreadyOpenError("Ya tienes una pausa en curso.") from exc
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
