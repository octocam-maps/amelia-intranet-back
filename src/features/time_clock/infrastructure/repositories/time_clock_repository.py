"""
Adaptador asyncpg del puerto `ITimeClockRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `time_clock_entries`.
"""

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Optional

import asyncpg

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import (
    OvernightStay,
    ProductCategory,
    Project,
    TechnicianDailyLog,
    TimeClockBreak,
    TimeClockEntry,
    TimeClockEntryNote,
    TimeClockExportRow,
)
from ...domain.errors import (
    DuplicateDailyLogError,
    TimeClockAlreadyClockedInError,
    TimeClockBreakAlreadyOpenError,
    TimeClockOverlapError,
)
from ...domain.policy import MINUTES_PER_COMPENSATION_DAY
from ...domain.ports import ITimeClockRepository

_ENTRY_SELECT = """
    SELECT id, user_id, work_date, clock_in, clock_out, source, created_at, updated_at
    FROM time_clock_entries
"""

# Listados (`list_entries_for_user`/`list_entries_for_all`): mismo JOIN a
# `users` que `_EXPORT_SELECT`, pero SOLO para resolver `full_name` — a
# diferencia del informe XLSX, aquí no se filtra `is_external`/`deleted_at`
# ni se resuelve DNI/teléfono (la vista admin de "toda la plantilla" no
# cambió ese alcance, solo dejó de mostrar el UUID crudo). El `FK ... ON
# DELETE CASCADE` de `time_clock_entries.user_id` garantiza que todo tramo
# tiene un `users` vivo detrás, así que un JOIN normal (no LEFT) es seguro.
_ENTRY_LIST_SELECT = """
    SELECT e.id, e.user_id, e.work_date, e.clock_in, e.clock_out, e.source,
           e.created_at, e.updated_at, u.full_name
    FROM time_clock_entries e
    JOIN users u ON u.id = e.user_id
"""

_BREAK_SELECT = "SELECT id, entry_id, break_start, break_end FROM time_clock_breaks"

# Parte diario del técnico: el satélite junto con las horas de su tramo padre
# y los nombres ya resueltos (proyecto y persona). `JOIN` normal en los tres
# casos — `entry_id` y `project_id` son NOT NULL con FK, y el FK de `user_id`
# es `ON DELETE CASCADE`, así que no hay filas huérfanas posibles.
_DAILY_LOG_SELECT = """
    SELECT d.entry_id, d.user_id, d.work_date, d.project_id, d.work_location,
           d.had_break, d.break_minutes, d.overnight_stay, d.product_category,
           d.created_at, d.updated_at,
           e.clock_in AS started_at, e.clock_out AS ended_at,
           p.name AS project_name, u.full_name
    FROM technician_daily_logs d
    JOIN time_clock_entries e ON e.id = d.entry_id
    JOIN projects p ON p.id = d.project_id
    JOIN users u ON u.id = d.user_id
"""

# Incidencias/comentarios sobre un tramo (B-2b): LEFT JOIN (no JOIN) a
# `users` porque `author_id` admite NULL (`ON DELETE SET NULL`) — una
# incidencia cuyo autor fue eliminado sigue listándose, solo sin nombre.
_NOTE_LIST_SELECT = """
    SELECT n.id, n.entry_id, n.author_id, n.body, n.created_at, u.full_name AS author_full_name
    FROM time_clock_entry_notes n
    LEFT JOIN users u ON u.id = n.author_id
    WHERE n.entry_id = $1
    ORDER BY n.created_at ASC
"""

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
        e.clock_out,
        e.source
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
        e.clock_out,
        e.source
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


def _row_to_entry_with_name(row) -> TimeClockEntry:
    return TimeClockEntry(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        work_date=row["work_date"],
        clock_in=row["clock_in"],
        clock_out=row["clock_out"],
        source=row["source"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        full_name=row["full_name"],
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
        source=row["source"],
    )


def _row_to_break(row) -> TimeClockBreak:
    return TimeClockBreak(
        id=str(row["id"]),
        entry_id=str(row["entry_id"]),
        break_start=row["break_start"],
        break_end=row["break_end"],
    )


def _row_to_note(row) -> TimeClockEntryNote:
    return TimeClockEntryNote(
        id=str(row["id"]),
        entry_id=str(row["entry_id"]),
        author_id=str(row["author_id"]) if row["author_id"] is not None else None,
        body=row["body"],
        created_at=row["created_at"],
        author_full_name=row["author_full_name"],
    )


def _row_to_daily_log(row) -> TechnicianDailyLog:
    return TechnicianDailyLog(
        entry_id=str(row["entry_id"]),
        user_id=str(row["user_id"]),
        work_date=row["work_date"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        project_id=str(row["project_id"]),
        work_location=row["work_location"],
        had_break=row["had_break"],
        break_minutes=row["break_minutes"],
        overnight_stay=OvernightStay(row["overnight_stay"]),
        product_category=ProductCategory(row["product_category"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        project_name=row["project_name"],
        full_name=row["full_name"],
    )


def _row_to_project(row) -> Project:
    return Project(
        id=str(row["id"]),
        code=row["code"],
        name=row["name"],
        is_active=row["is_active"],
    )


class PostgresTimeClockRepository(ITimeClockRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool
        # RACE-1: conexión activa mientras se está dentro de un `async with
        # self.transaction()` — `None` en el camino normal (autocommit por
        # llamada, vía `self._db`). Ver `transaction()` y `_writer` más abajo.
        self._connection: asyncpg.Connection | None = None

    @asynccontextmanager
    async def transaction(self):
        async with self._db.acquire() as connection:
            async with connection.transaction():
                previous_connection = self._connection
                self._connection = connection
                try:
                    yield
                finally:
                    self._connection = previous_connection

    @property
    def _writer(self) -> "DatabasePool | asyncpg.Connection":
        """Ejecutor efectivo para `create_entry`/`find_overlapping_entry`:
        la conexión de la transacción activa si `transaction()` está en
        curso, o el pool (una conexión nueva por llamada) en el camino
        normal. Ambos exponen `fetchrow(query, *args)` con la misma firma."""
        return self._connection if self._connection is not None else self._db

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
            row = await self._writer.fetchrow(
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
        self,
        user_id: str,
        *,
        date_from: date,
        date_to: date,
        limit: Optional[int],
        offset: int,
    ) -> list[TimeClockEntry]:
        query = f"""
            {_ENTRY_LIST_SELECT}
            WHERE e.user_id = $1 AND e.work_date BETWEEN $2 AND $3
            ORDER BY e.work_date DESC, e.clock_in DESC
        """
        params: list = [user_id, date_from, date_to]
        if limit is not None:
            params.extend([limit, offset])
            query += f" LIMIT ${len(params) - 1} OFFSET ${len(params)}"
        rows = await self._db.fetch(query, *params)
        return [_row_to_entry_with_name(row) for row in rows]

    async def count_entries_for_user(self, user_id: str, *, date_from: date, date_to: date) -> int:
        count = await self._db.fetchval(
            """
            SELECT COUNT(*) FROM time_clock_entries
            WHERE user_id = $1 AND work_date BETWEEN $2 AND $3
            """,
            user_id,
            date_from,
            date_to,
        )
        return int(count or 0)

    async def list_entries_for_users(
        self,
        user_ids: list[str],
        *,
        date_from: date,
        date_to: date,
        limit: Optional[int],
        offset: int,
    ) -> list[TimeClockEntry]:
        query = f"""
            {_ENTRY_LIST_SELECT}
            WHERE e.user_id = ANY($1::uuid[]) AND e.work_date BETWEEN $2 AND $3
            ORDER BY e.work_date DESC, e.clock_in DESC
        """
        params: list = [user_ids, date_from, date_to]
        if limit is not None:
            params.extend([limit, offset])
            query += f" LIMIT ${len(params) - 1} OFFSET ${len(params)}"
        rows = await self._db.fetch(query, *params)
        return [_row_to_entry_with_name(row) for row in rows]

    async def count_entries_for_users(
        self, user_ids: list[str], *, date_from: date, date_to: date
    ) -> int:
        count = await self._db.fetchval(
            """
            SELECT COUNT(*) FROM time_clock_entries
            WHERE user_id = ANY($1::uuid[]) AND work_date BETWEEN $2 AND $3
            """,
            user_ids,
            date_from,
            date_to,
        )
        return int(count or 0)

    async def list_entries_for_all(
        self, *, date_from: date, date_to: date, limit: Optional[int], offset: int
    ) -> list[TimeClockEntry]:
        query = f"""
            {_ENTRY_LIST_SELECT}
            WHERE e.work_date BETWEEN $1 AND $2
            ORDER BY e.work_date DESC, e.clock_in DESC
        """
        params: list = [date_from, date_to]
        if limit is not None:
            params.extend([limit, offset])
            query += f" LIMIT ${len(params) - 1} OFFSET ${len(params)}"
        rows = await self._db.fetch(query, *params)
        return [_row_to_entry_with_name(row) for row in rows]

    async def count_entries_for_all(self, *, date_from: date, date_to: date) -> int:
        count = await self._db.fetchval(
            "SELECT COUNT(*) FROM time_clock_entries WHERE work_date BETWEEN $1 AND $2",
            date_from,
            date_to,
        )
        return int(count or 0)

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

    # --- Alta de fichaje en lote por rango de días (RF-A3) ---

    async def list_holiday_dates_for_entity(
        self, date_from: date, date_to: date, entity_id: str | None
    ) -> list[date]:
        # `entity_id IS NULL` cubre los festivos "para todas las
        # entidades"; el `OR entity_id = $3` añade los propios de la
        # entidad del usuario. A diferencia de `absences.list_holiday_
        # dates` (que NO escopa por entidad, gap preexistente fuera de
        # alcance), este puerto sí lo hace porque la spec de RF-A3 lo
        # exige explícitamente.
        rows = await self._db.fetch(
            """
            SELECT day FROM holidays
            WHERE day BETWEEN $1 AND $2
              AND (entity_id IS NULL OR entity_id = $3)
            """,
            date_from,
            date_to,
            entity_id,
        )
        return [row["day"] for row in rows]

    async def list_approved_absence_ranges(
        self, user_id: str, date_from: date, date_to: date
    ) -> list[tuple[date, date]]:
        rows = await self._db.fetch(
            """
            SELECT start_date, end_date FROM absence_requests
            WHERE user_id = $1
              AND status = 'approved'
              AND start_date <= $3
              AND end_date >= $2
            """,
            user_id,
            date_from,
            date_to,
        )
        return [(row["start_date"], row["end_date"]) for row in rows]

    async def list_existing_entry_dates(
        self, user_id: str, date_from: date, date_to: date
    ) -> list[date]:
        rows = await self._db.fetch(
            """
            SELECT DISTINCT work_date FROM time_clock_entries
            WHERE user_id = $1 AND work_date BETWEEN $2 AND $3
            """,
            user_id,
            date_from,
            date_to,
        )
        return [row["work_date"] for row in rows]

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
        # RACE-1: usa `self._writer` (no `self._db` directo) para que, dentro
        # de un lote transaccional, la comprobación de solape vea las
        # escrituras de los días previos del MISMO lote (misma conexión,
        # misma transacción todavía sin commit).
        row = await self._writer.fetchrow(
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

    # --- Incidencias/comentarios sobre un tramo (B-2b) ---

    async def add_note(self, *, entry_id: str, author_id: str, body: str) -> TimeClockEntryNote:
        row = await self._db.fetchrow(
            """
            INSERT INTO time_clock_entry_notes (entry_id, author_id, body)
            VALUES ($1, $2, $3)
            RETURNING id, entry_id, author_id, body, created_at
            """,
            entry_id,
            author_id,
            body,
        )
        # El INSERT no conoce todavía `author_full_name` (no hay JOIN aquí) —
        # el frontend refresca el listado (`list_notes_for_entry`) tras
        # publicar, que sí lo resuelve.
        return TimeClockEntryNote(
            id=str(row["id"]),
            entry_id=str(row["entry_id"]),
            author_id=str(row["author_id"]) if row["author_id"] is not None else None,
            body=row["body"],
            created_at=row["created_at"],
        )

    async def list_notes_for_entry(self, entry_id: str) -> list[TimeClockEntryNote]:
        rows = await self._db.fetch(_NOTE_LIST_SELECT, entry_id)
        return [_row_to_note(row) for row in rows]

    # --- Parte diario del técnico (requerimiento v1.2 §M1) ---

    async def create_daily_log(
        self,
        *,
        user_id: str,
        work_date: date,
        started_at: datetime,
        ended_at: datetime,
        project_id: str,
        work_location: str,
        had_break: bool,
        break_minutes: int,
        overnight_stay: OvernightStay,
        product_category: ProductCategory,
    ) -> TechnicianDailyLog:
        # Las DOS escrituras en una sola transacción: un tramo sin su parte
        # sería una jornada fantasma en el registro legal —sin proyecto ni
        # lugar— y nadie sabría de dónde salió.
        async with self._db.acquire() as connection:
            async with connection.transaction():
                try:
                    entry = await connection.fetchrow(
                        """
                        INSERT INTO time_clock_entries
                            (user_id, work_date, clock_in, clock_out, source)
                        VALUES ($1, $2, $3, $4, 'manual')
                        RETURNING id, created_at, updated_at
                        """,
                        user_id,
                        work_date,
                        started_at,
                        ended_at,
                    )
                except asyncpg.exceptions.ExclusionViolationError as exc:
                    raise TimeClockOverlapError(
                        "Ese horario se solapa con otra jornada ya registrada."
                    ) from exc

                entry_id = str(entry["id"])
                try:
                    await connection.execute(
                        """
                        INSERT INTO technician_daily_logs
                            (entry_id, user_id, work_date, project_id, work_location,
                             had_break, break_minutes, overnight_stay, product_category)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        entry_id,
                        user_id,
                        work_date,
                        project_id,
                        work_location,
                        had_break,
                        break_minutes,
                        overnight_stay.value,
                        product_category.value,
                    )
                except asyncpg.exceptions.UniqueViolationError as exc:
                    # `uq_technician_daily_logs_one_per_day` bajo concurrencia:
                    # el use case ya lo comprueba, pero eso es check-then-act y
                    # el constraint es la fuente de verdad real.
                    raise DuplicateDailyLogError(
                        "Ya existe un parte para ese día. Edítalo en lugar de crear otro."
                    ) from exc

        created = await self.find_daily_log(entry_id)
        assert created is not None  # noqa: S101 — recién insertado en esta transacción
        return created

    async def find_daily_log(self, entry_id: str) -> Optional[TechnicianDailyLog]:
        row = await self._db.fetchrow(f"{_DAILY_LOG_SELECT} WHERE d.entry_id = $1", entry_id)
        return _row_to_daily_log(row) if row else None

    async def find_daily_log_for_date(
        self, user_id: str, work_date: date
    ) -> Optional[TechnicianDailyLog]:
        row = await self._db.fetchrow(
            f"{_DAILY_LOG_SELECT} WHERE d.user_id = $1 AND d.work_date = $2",
            user_id,
            work_date,
        )
        return _row_to_daily_log(row) if row else None

    async def list_daily_logs(
        self, user_id: str, *, date_from: date, date_to: date
    ) -> list[TechnicianDailyLog]:
        rows = await self._db.fetch(
            f"""
            {_DAILY_LOG_SELECT}
            WHERE d.user_id = $1 AND d.work_date BETWEEN $2 AND $3
            ORDER BY d.work_date ASC
            """,
            user_id,
            date_from,
            date_to,
        )
        return [_row_to_daily_log(row) for row in rows]

    async def update_daily_log(
        self,
        entry_id: str,
        *,
        started_at: datetime,
        ended_at: datetime,
        project_id: str,
        work_location: str,
        had_break: bool,
        break_minutes: int,
        overnight_stay: OvernightStay,
        product_category: ProductCategory,
    ) -> TechnicianDailyLog:
        async with self._db.acquire() as connection:
            async with connection.transaction():
                try:
                    await connection.execute(
                        """
                        UPDATE time_clock_entries
                        SET clock_in = $2, clock_out = $3, updated_at = CURRENT_TIMESTAMP
                        WHERE id = $1
                        """,
                        entry_id,
                        started_at,
                        ended_at,
                    )
                except asyncpg.exceptions.ExclusionViolationError as exc:
                    raise TimeClockOverlapError(
                        "Ese horario se solapa con otra jornada ya registrada."
                    ) from exc

                await connection.execute(
                    """
                    UPDATE technician_daily_logs
                    SET project_id = $2, work_location = $3, had_break = $4,
                        break_minutes = $5, overnight_stay = $6, product_category = $7,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE entry_id = $1
                    """,
                    entry_id,
                    project_id,
                    work_location,
                    had_break,
                    break_minutes,
                    overnight_stay.value,
                    product_category.value,
                )

        updated = await self.find_daily_log(entry_id)
        assert updated is not None  # noqa: S101 — acaba de actualizarse
        return updated

    async def delete_daily_log(self, entry_id: str) -> None:
        # Solo el tramo padre: el `ON DELETE CASCADE` del satélite se lleva el
        # detalle de campo.
        await self._db.execute("DELETE FROM time_clock_entries WHERE id = $1", entry_id)

    async def find_project(self, project_id: str) -> Optional[Project]:
        row = await self._db.fetchrow(
            "SELECT id, code, name, is_active FROM projects WHERE id = $1", project_id
        )
        return _row_to_project(row) if row else None

    async def list_active_projects(self) -> list[Project]:
        rows = await self._db.fetch(
            "SELECT id, code, name, is_active FROM projects WHERE is_active ORDER BY name ASC"
        )
        return [_row_to_project(row) for row in rows]

    async def sum_worked_minutes_by_month(self, user_id: str, year: int) -> dict[int, int]:
        # La resta de la pausa va DENTRO del SUM, no después: restar el total
        # de pausas al total bruto daría el mismo número aquí, pero deja de
        # darlo en cuanto haya que agrupar por otra cosa. Se calcula igual que
        # `TechnicianDailyLog.worked_minutes` para que la tabla del mes y este
        # agregado no puedan discrepar.
        rows = await self._db.fetch(
            """
            SELECT EXTRACT(MONTH FROM d.work_date)::int AS month,
                   COALESCE(SUM(
                       EXTRACT(EPOCH FROM (e.clock_out - e.clock_in)) / 60 - d.break_minutes
                   ), 0)::int AS minutes
            FROM technician_daily_logs d
            JOIN time_clock_entries e ON e.id = d.entry_id
            WHERE d.user_id = $1
              AND EXTRACT(YEAR FROM d.work_date) = $2
              AND e.clock_out IS NOT NULL
            GROUP BY 1
            """,
            user_id,
            year,
        )
        return {row["month"]: row["minutes"] for row in rows}

    async def sum_compensation_absence_minutes(self, user_id: str, year: int) -> int:
        # Días HÁBILES, no naturales: se descuentan sábados, domingos y
        # festivos, igual que hace el cómputo del resto de ausencias. Contar
        # días naturales le cobraría al técnico el fin de semana que cae dentro
        # de su descanso.
        # El alias de `generate_series` se llama `gs(the_day)` y NO `day`, y
        # cada referencia va CALIFICADA. No es estilo: `holidays` tiene una
        # columna llamada `day`, y un `day` sin calificar dentro del EXISTS se
        # resuelve al scope más interno —`h.day`—, convirtiendo la condición en
        # `h.day = h.day`, siempre cierta. Con eso, en cuanto existiera UN solo
        # festivo en la tabla, TODOS los días se contaban como festivo y el
        # saldo disfrutado salía 0: el guard de `descanso_horas_extra` habría
        # dejado pedir descansos sin respaldo sin que nada fallara.
        row = await self._db.fetchrow(
            """
            SELECT COALESCE(SUM(
                (SELECT COUNT(*)
                 FROM generate_series(
                     GREATEST(a.start_date, make_date($2, 1, 1)),
                     LEAST(a.end_date, make_date($2, 12, 31)),
                     INTERVAL '1 day'
                 ) AS gs(the_day)
                 WHERE EXTRACT(ISODOW FROM gs.the_day) < 6
                   AND NOT EXISTS (
                       SELECT 1 FROM holidays h
                       WHERE h.day = gs.the_day::date
                         AND (h.entity_id IS NULL OR h.entity_id = (
                             SELECT entity_id FROM users WHERE id = a.user_id
                         ))
                   ))
            ), 0)::int AS days
            FROM absence_requests a
            JOIN absence_types t ON t.id = a.absence_type_id
            WHERE a.user_id = $1
              AND a.status = 'approved'
              AND t.code = 'descanso_horas_extra'
              AND a.start_date <= make_date($2, 12, 31)
              AND a.end_date   >= make_date($2, 1, 1)
            """,
            user_id,
            year,
        )
        return int(row["days"]) * MINUTES_PER_COMPENSATION_DAY
