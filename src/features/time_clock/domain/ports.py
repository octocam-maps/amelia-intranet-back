"""
Puertos (Protocols) del feature `time_clock`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from contextlib import AbstractAsyncContextManager
from datetime import date, datetime
from typing import Optional, Protocol

from .entities import TimeClockBreak, TimeClockEntry, TimeClockEntryNote, TimeClockExportRow


class ITimeClockRepository(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[None]:
        """RACE-1 (auditoría QA, severidad ALTA): async context manager que
        agrupa en una única transacción atómica las escrituras hechas
        DENTRO del bloque (`async with repository.transaction(): ...`).

        Lo usa el bucle de escritura de `CreateTimeClockEntriesBatchUseCase`
        para que un fallo a mitad del lote (p. ej. `TimeClockOverlapError`
        por el constraint `EXCLUDE` bajo concurrencia real) revierta TODOS
        los tramos ya creados en esa misma pasada, no solo los pendientes.

        Alcance deliberadamente acotado: solo `create_entry` y
        `find_overlapping_entry` — los dos métodos que el bucle de
        escritura del lote invoca vía `CreateTimeClockEntryUseCase` — honran
        este contexto en el adaptador Postgres. Ampliarlo a todos los
        métodos del puerto sería invasión sin necesidad hoy; si otro flujo
        empieza a escribir dentro de un `async with transaction()`, hay que
        revisar si también necesita sumarse."""
        ...

    async def create_entry(
        self,
        *,
        user_id: str,
        work_date: date,
        clock_in: datetime,
        clock_out: Optional[datetime],
        source: str,
    ) -> TimeClockEntry: ...

    async def find_entry_by_id(self, entry_id: str) -> Optional[TimeClockEntry]: ...

    async def list_entries_for_user(
        self, user_id: str, *, date_from: date, date_to: date, limit: Optional[int], offset: int
    ) -> list[TimeClockEntry]:
        """Cada fila incluye `full_name` (JOIN a `users`) para pintarlo en el
        listado sin que el frontend tenga que resolverlo aparte —
        `list_entries_for_user`/`list_entries_for_all` son los ÚNICOS puntos
        del puerto que rellenan ese campo (ver `TimeClockEntry.full_name`).
        `limit=None` devuelve TODO el rango sin paginar (lo usa el export
        CSV de `GET /entries/export`, que necesita el rango completo, no
        solo la página visible en pantalla); `offset` se ignora en ese caso."""
        ...

    async def count_entries_for_user(self, user_id: str, *, date_from: date, date_to: date) -> int:
        """Total SIN paginar del mismo filtro que `list_entries_for_user`
        — lo usa el frontend para construir el paginador."""
        ...

    async def list_entries_for_users(
        self,
        user_ids: list[str],
        *,
        date_from: date,
        date_to: date,
        limit: Optional[int],
        offset: int,
    ) -> list[TimeClockEntry]:
        """Multi-selector de personas (Lote 2): igual que `list_entries_for_
        user`, pero para VARIOS ids a la vez (`WHERE user_id = ANY(...)`) —
        el guard RGPD (solo el admin puede pedir más de uno) vive en el use
        case, este puerto no vuelve a comprobar el rol."""
        ...

    async def count_entries_for_users(
        self, user_ids: list[str], *, date_from: date, date_to: date
    ) -> int:
        """Total SIN paginar del mismo filtro que `list_entries_for_users`."""
        ...

    async def list_entries_for_all(
        self, *, date_from: date, date_to: date, limit: Optional[int], offset: int
    ) -> list[TimeClockEntry]:
        """Vista aumentada del admin: fichajes de TODA la plantilla. Mismo
        contrato de `full_name`/`limit`/`offset` que `list_entries_for_user`."""
        ...

    async def count_entries_for_all(self, *, date_from: date, date_to: date) -> int:
        """Total SIN paginar del mismo filtro que `list_entries_for_all`."""
        ...

    async def list_export_rows_for_all(
        self, *, date_from: date, date_to: date
    ) -> list[TimeClockExportRow]:
        """Informe admin (XLSX, `GET /time-clock/entries/export.xlsx`):
        fichajes de TODA la plantilla INTERNA (excluye externos-invitado, que
        no tienen Control horario en la matriz de permisos), con nombre/DNI/
        teléfono ya resueltos vía `users` + `user_profiles`."""
        ...

    async def list_export_rows_for_user(
        self, user_id: str, *, date_from: date, date_to: date
    ) -> list[TimeClockExportRow]:
        """Informe empleado (mismo XLSX, mismo endpoint): SOLO los fichajes
        del propio `user_id` — alcance RGPD. Mismo join con `users` +
        `user_profiles` que `list_export_rows_for_all`, pero acotado a un
        único usuario."""
        ...

    async def find_overlapping_entry(
        self,
        user_id: str,
        work_date: date,
        clock_in: datetime,
        clock_out: Optional[datetime],
        *,
        exclude_entry_id: Optional[str] = None,
    ) -> Optional[TimeClockEntry]:
        """`None` si no hay ningún otro tramo del mismo usuario/día que se
        solape con el rango dado. `exclude_entry_id` se usa al editar un
        tramo existente, para no compararlo contra sí mismo."""
        ...

    async def update_entry(
        self, entry_id: str, *, clock_in: datetime, clock_out: Optional[datetime]
    ) -> TimeClockEntry: ...

    async def delete_entry(self, entry_id: str) -> None: ...

    # --- Fichaje en vivo ---

    async def find_open_entry_for_user(self, user_id: str) -> Optional[TimeClockEntry]:
        """El tramo abierto (`clock_out IS NULL`) del usuario, si lo hay —
        independientemente del `work_date` (cubre jornadas que cruzan la
        medianoche de reloj de pared aunque el tramo en sí no cruce de
        `work_date`, ver `_validate_range`)."""
        ...

    async def find_open_break_for_entry(self, entry_id: str) -> Optional[TimeClockBreak]: ...

    async def create_break(self, entry_id: str, break_start: datetime) -> TimeClockBreak: ...

    async def close_break(self, break_id: str, break_end: datetime) -> TimeClockBreak: ...

    async def get_week_worked_seconds(
        self, user_id: str, week_start: date, week_end: date
    ) -> float:
        """Segundos trabajados en el rango (normalmente lunes-domingo de la
        semana en curso), sumando todos los tramos del usuario y restando el
        tiempo de sus pausas — el tramo/pausa abierto cuenta hasta AHORA."""
        ...

    # --- Alta de fichaje en lote por rango de días (RF-A3) ---

    async def list_holiday_dates_for_entity(
        self, date_from: date, date_to: date, entity_id: str | None
    ) -> list[date]:
        """Festivos vigentes en el rango, ESCOPADOS por entidad —
        `entity_id=NULL` en la fila de `holidays` significa "aplica a
        todas las entidades", así que siempre se incluye junto con los
        festivos de la entidad concreta del usuario. A diferencia de
        `absences.list_holiday_dates` (que NO escopa por entidad hoy — gap
        preexistente, fuera de alcance de este feature), este puerto SÍ lo
        hace, porque la spec de RF-A3 lo exige explícitamente por tabla de
        casos."""
        ...

    async def list_approved_absence_ranges(
        self, user_id: str, date_from: date, date_to: date
    ) -> list[tuple[date, date]]:
        """Rangos `[start_date, end_date]` de solicitudes `approved` del
        propio usuario que solapan con `[date_from, date_to]` — se
        expanden a fechas individuales en el use case, no aquí."""
        ...

    async def list_existing_entry_dates(
        self, user_id: str, date_from: date, date_to: date
    ) -> list[date]:
        """`work_date` distintos con al menos un tramo ya registrado del
        usuario en el rango — el alta en lote los omite como
        `ya_registrado` sin traer los tramos completos."""
        ...

    # --- Incidencias/comentarios sobre un tramo (B-2b) ---

    async def add_note(self, *, entry_id: str, author_id: str, body: str) -> TimeClockEntryNote:
        """Alta admin-only (el guard vive en el router: `require_role
        ("administrador")`) — este puerto no vuelve a comprobar el rol."""
        ...

    async def list_notes_for_entry(self, entry_id: str) -> list[TimeClockEntryNote]:
        """Orden cronológico ascendente (hilo de incidencias). Cada nota trae
        `author_full_name` resuelto vía JOIN a `users` — `None` si el autor
        fue eliminado (`ON DELETE SET NULL`)."""
        ...
