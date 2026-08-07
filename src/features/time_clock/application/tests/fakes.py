"""Fake en memoria de `ITimeClockRepository` — permite testear los casos de
uso sin Postgres, igual que `features/auth/application/tests/fakes.py`."""

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Optional

from src.features.time_clock.domain.entities import (
    OvernightStay,
    ProductCategory,
    Project,
    TechnicianDailyLog,
    TimeClockBreak,
    TimeClockEntry,
    TimeClockEntryNote,
    TimeClockExportRow,
)


@dataclass
class FakeTimeClockRepository:
    entries: dict[str, TimeClockEntry]

    def __init__(
        self,
        entries: Optional[list[TimeClockEntry]] = None,
        breaks: Optional[list[TimeClockBreak]] = None,
        full_names: Optional[dict[str, str]] = None,
        dni_by_user: Optional[dict[str, str]] = None,
        phone_by_user: Optional[dict[str, str]] = None,
        holidays: Optional[list[tuple[date, str | None]]] = None,
        approved_absence_ranges: Optional[dict[str, list[tuple[date, date]]]] = None,
        projects: Optional[list[Project]] = None,
        compensation_consumed_minutes: Optional[dict[tuple[str, int], int]] = None,
    ):
        # Parte diario del técnico (v1.2 §M1). `compensation_consumed_minutes`
        # se indexa por (user_id, año) porque el saldo es ANUAL — el fake no
        # tiene `absence_requests` detrás.
        self.daily_logs: dict[str, TechnicianDailyLog] = {}
        self.projects: dict[str, Project] = {p.id: p for p in (projects or [])}
        self.compensation_consumed_minutes: dict[tuple[str, int], int] = (
            compensation_consumed_minutes or {}
        )
        self.entries = {e.id: e for e in (entries or [])}
        self.breaks: dict[str, TimeClockBreak] = {b.id: b for b in (breaks or [])}
        # Incidencias/comentarios (B-2b) — en memoria, sin tabla real detrás.
        self.notes: dict[str, TimeClockEntryNote] = {}
        # Identidad/contacto para `list_export_rows_for_all` — el fake no
        # tiene una tabla `users`/`user_profiles` real, así que se pasan por
        # fuera solo cuando un test necesita el informe XLSX.
        self.full_names: dict[str, str] = full_names or {}
        self.dni_by_user: dict[str, str] = dni_by_user or {}
        self.phone_by_user: dict[str, str] = phone_by_user or {}
        # RF-A3 (alta en lote): festivos como (day, entity_id) — entity_id
        # `None` significa "aplica a todas las entidades", igual que la fila
        # real de `holidays`. El fake no tiene esa tabla detrás.
        self.holidays: list[tuple[date, str | None]] = holidays or []
        # RF-A3: rangos [start_date, end_date] de solicitudes YA aprobadas,
        # por usuario — el fake no tiene una tabla `absence_requests` real.
        self.approved_absence_ranges: dict[str, list[tuple[date, date]]] = (
            approved_absence_ranges or {}
        )

    # RACE-1: simula la atomicidad del `async with connection.transaction()`
    # real — toma una foto de `entries`/`breaks` al entrar y la restaura si
    # el bloque lanza, igual que un ROLLBACK real revertiría todo el lote.
    @asynccontextmanager
    async def transaction(self):
        entries_snapshot = dict(self.entries)
        breaks_snapshot = dict(self.breaks)
        try:
            yield
        except Exception:
            self.entries = entries_snapshot
            self.breaks = breaks_snapshot
            raise

    async def create_entry(self, *, user_id, work_date, clock_in, clock_out, source) -> TimeClockEntry:
        entry_id = str(uuid.uuid4())
        now = datetime.now(clock_in.tzinfo)
        entry = TimeClockEntry(
            id=entry_id,
            user_id=user_id,
            work_date=work_date,
            clock_in=clock_in,
            clock_out=clock_out,
            source=source,
            created_at=now,
            updated_at=now,
        )
        self.entries[entry_id] = entry
        return entry

    async def find_entry_by_id(self, entry_id: str) -> Optional[TimeClockEntry]:
        return self.entries.get(entry_id)

    def _with_full_name(self, entry: TimeClockEntry) -> TimeClockEntry:
        # Mismo enriquecimiento que el JOIN a `users` del repositorio real
        # (`_row_to_entry_with_name`) — solo lo hacen los listados.
        return replace(entry, full_name=self.full_names.get(entry.user_id))

    def _paginate(
        self, entries: list[TimeClockEntry], *, limit: Optional[int], offset: int
    ) -> list[TimeClockEntry]:
        if limit is None:
            return entries
        return entries[offset : offset + limit]

    async def list_entries_for_user(
        self, user_id: str, *, date_from: date, date_to: date, limit: Optional[int], offset: int
    ) -> list[TimeClockEntry]:
        matches = [
            self._with_full_name(e)
            for e in self.entries.values()
            if e.user_id == user_id and date_from <= e.work_date <= date_to
        ]
        matches.sort(key=lambda e: (e.work_date, e.clock_in), reverse=True)
        return self._paginate(matches, limit=limit, offset=offset)

    async def count_entries_for_user(self, user_id: str, *, date_from: date, date_to: date) -> int:
        return len(
            [
                e
                for e in self.entries.values()
                if e.user_id == user_id and date_from <= e.work_date <= date_to
            ]
        )

    async def list_entries_for_users(
        self, user_ids: list[str], *, date_from: date, date_to: date, limit: Optional[int], offset: int
    ) -> list[TimeClockEntry]:
        ids = set(user_ids)
        matches = [
            self._with_full_name(e)
            for e in self.entries.values()
            if e.user_id in ids and date_from <= e.work_date <= date_to
        ]
        matches.sort(key=lambda e: (e.work_date, e.clock_in), reverse=True)
        return self._paginate(matches, limit=limit, offset=offset)

    async def count_entries_for_users(
        self, user_ids: list[str], *, date_from: date, date_to: date
    ) -> int:
        ids = set(user_ids)
        return len(
            [e for e in self.entries.values() if e.user_id in ids and date_from <= e.work_date <= date_to]
        )

    async def list_entries_for_all(
        self, *, date_from: date, date_to: date, limit: Optional[int], offset: int
    ) -> list[TimeClockEntry]:
        matches = [
            self._with_full_name(e)
            for e in self.entries.values()
            if date_from <= e.work_date <= date_to
        ]
        matches.sort(key=lambda e: (e.work_date, e.clock_in), reverse=True)
        return self._paginate(matches, limit=limit, offset=offset)

    async def count_entries_for_all(self, *, date_from: date, date_to: date) -> int:
        return len([e for e in self.entries.values() if date_from <= e.work_date <= date_to])

    async def list_export_rows_for_all(
        self, *, date_from: date, date_to: date
    ) -> list[TimeClockExportRow]:
        return [
            TimeClockExportRow(
                user_id=e.user_id,
                full_name=self.full_names.get(e.user_id, "Sin Nombre"),
                dni_nif=self.dni_by_user.get(e.user_id),
                phone=self.phone_by_user.get(e.user_id),
                work_date=e.work_date,
                clock_in=e.clock_in,
                clock_out=e.clock_out,
                source=e.source,
            )
            for e in self.entries.values()
            if date_from <= e.work_date <= date_to
        ]

    async def list_export_rows_for_user(
        self, user_id: str, *, date_from: date, date_to: date
    ) -> list[TimeClockExportRow]:
        return [
            TimeClockExportRow(
                user_id=e.user_id,
                full_name=self.full_names.get(e.user_id, "Sin Nombre"),
                dni_nif=self.dni_by_user.get(e.user_id),
                phone=self.phone_by_user.get(e.user_id),
                work_date=e.work_date,
                clock_in=e.clock_in,
                clock_out=e.clock_out,
                source=e.source,
            )
            for e in self.entries.values()
            if e.user_id == user_id and date_from <= e.work_date <= date_to
        ]

    # --- RF-A3 (alta en lote por rango de días) ---

    async def list_holiday_dates_for_entity(
        self, date_from: date, date_to: date, entity_id: str | None
    ) -> list[date]:
        return [
            day
            for day, holiday_entity_id in self.holidays
            if date_from <= day <= date_to
            and (holiday_entity_id is None or holiday_entity_id == entity_id)
        ]

    async def list_approved_absence_ranges(
        self, user_id: str, date_from: date, date_to: date
    ) -> list[tuple[date, date]]:
        ranges = self.approved_absence_ranges.get(user_id, [])
        return [(start, end) for start, end in ranges if start <= date_to and end >= date_from]

    async def list_existing_entry_dates(
        self, user_id: str, date_from: date, date_to: date
    ) -> list[date]:
        return sorted(
            {
                e.work_date
                for e in self.entries.values()
                if e.user_id == user_id and date_from <= e.work_date <= date_to
            }
        )

    async def find_overlapping_entry(
        self, user_id, work_date, clock_in, clock_out, *, exclude_entry_id=None
    ) -> Optional[TimeClockEntry]:
        # NO se filtra por `work_date`: desde la migración 053 el EXCLUDE real
        # tampoco lo hace, porque un parte de técnico puede cruzar la
        # medianoche. Comparar solo dentro del mismo día dejaría pasar aquí un
        # solape que Postgres sí rechaza — y el test daría verde sobre una
        # regla que ya no existe.
        effective_end = clock_out or datetime.max.replace(tzinfo=clock_in.tzinfo)
        for entry in self.entries.values():
            if entry.id == exclude_entry_id:
                continue
            if entry.user_id != user_id:
                continue
            other_end = entry.clock_out or datetime.max.replace(tzinfo=entry.clock_in.tzinfo)
            if entry.clock_in < effective_end and other_end > clock_in:
                return entry
        return None

    async def update_entry(
        self, entry_id: str, *, clock_in: datetime, clock_out: Optional[datetime]
    ) -> TimeClockEntry:
        existing = self.entries[entry_id]
        updated = replace(existing, clock_in=clock_in, clock_out=clock_out)
        self.entries[entry_id] = updated
        return updated

    async def delete_entry(self, entry_id: str) -> None:
        self.entries.pop(entry_id, None)

    # --- Fichaje en vivo ---

    async def find_open_entry_for_user(self, user_id: str) -> Optional[TimeClockEntry]:
        open_entries = [
            e for e in self.entries.values() if e.user_id == user_id and e.clock_out is None
        ]
        return max(open_entries, key=lambda e: e.clock_in) if open_entries else None

    async def find_open_break_for_entry(self, entry_id: str) -> Optional[TimeClockBreak]:
        for b in self.breaks.values():
            if b.entry_id == entry_id and b.break_end is None:
                return b
        return None

    async def create_break(self, entry_id: str, break_start: datetime) -> TimeClockBreak:
        break_id = str(uuid.uuid4())
        new_break = TimeClockBreak(id=break_id, entry_id=entry_id, break_start=break_start, break_end=None)
        self.breaks[break_id] = new_break
        return new_break

    async def close_break(self, break_id: str, break_end: datetime) -> TimeClockBreak:
        existing = self.breaks[break_id]
        updated = replace(existing, break_end=break_end)
        self.breaks[break_id] = updated
        return updated

    async def get_week_worked_seconds(self, user_id: str, week_start: date, week_end: date) -> float:
        now = datetime.now(timezone.utc)
        total = 0.0
        for entry in self.entries.values():
            if entry.user_id != user_id or not (week_start <= entry.work_date <= week_end):
                continue
            gross = ((entry.clock_out or now) - entry.clock_in).total_seconds()
            break_seconds = sum(
                ((b.break_end or now) - b.break_start).total_seconds()
                for b in self.breaks.values()
                if b.entry_id == entry.id
            )
            total += max(gross - break_seconds, 0.0)
        return total

    # --- Incidencias/comentarios sobre un tramo (B-2b) ---

    async def add_note(self, *, entry_id: str, author_id: str, body: str) -> TimeClockEntryNote:
        note_id = str(uuid.uuid4())
        note = TimeClockEntryNote(
            id=note_id,
            entry_id=entry_id,
            author_id=author_id,
            body=body,
            created_at=datetime.now(timezone.utc),
            author_full_name=self.full_names.get(author_id),
        )
        self.notes[note_id] = note
        return note

    async def list_notes_for_entry(self, entry_id: str) -> list[TimeClockEntryNote]:
        matches = [n for n in self.notes.values() if n.entry_id == entry_id]
        matches.sort(key=lambda n: n.created_at)
        return matches

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
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        # El tramo padre también se crea, igual que en el adaptador real: es
        # lo que hace que el parte cuente en el registro legal de jornada.
        self.entries[entry_id] = TimeClockEntry(
            id=entry_id,
            user_id=user_id,
            work_date=work_date,
            clock_in=started_at,
            clock_out=ended_at,
            source="manual",
            created_at=now,
            updated_at=now,
        )
        log = TechnicianDailyLog(
            entry_id=entry_id,
            user_id=user_id,
            work_date=work_date,
            started_at=started_at,
            ended_at=ended_at,
            project_id=project_id,
            work_location=work_location,
            had_break=had_break,
            break_minutes=break_minutes,
            overnight_stay=overnight_stay,
            product_category=product_category,
            created_at=now,
            updated_at=now,
            project_name=self.projects.get(project_id, Project(project_id, "X", "X", True)).name,
            full_name=self.full_names.get(user_id),
        )
        self.daily_logs[entry_id] = log
        return log

    async def find_daily_log(self, entry_id: str) -> Optional[TechnicianDailyLog]:
        return self.daily_logs.get(entry_id)

    async def find_daily_log_for_date(
        self, user_id: str, work_date: date
    ) -> Optional[TechnicianDailyLog]:
        for log in self.daily_logs.values():
            if log.user_id == user_id and log.work_date == work_date:
                return log
        return None

    async def list_daily_logs(
        self, user_id: str, *, date_from: date, date_to: date
    ) -> list[TechnicianDailyLog]:
        matches = [
            log
            for log in self.daily_logs.values()
            if log.user_id == user_id and date_from <= log.work_date <= date_to
        ]
        matches.sort(key=lambda log: log.work_date)
        return matches

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
        existing = self.daily_logs[entry_id]
        updated = replace(
            existing,
            started_at=started_at,
            ended_at=ended_at,
            project_id=project_id,
            work_location=work_location,
            had_break=had_break,
            break_minutes=break_minutes,
            overnight_stay=overnight_stay,
            product_category=product_category,
        )
        self.daily_logs[entry_id] = updated
        self.entries[entry_id] = replace(
            self.entries[entry_id], clock_in=started_at, clock_out=ended_at
        )
        return updated

    async def delete_daily_log(self, entry_id: str) -> None:
        self.daily_logs.pop(entry_id, None)
        self.entries.pop(entry_id, None)

    async def find_project(self, project_id: str) -> Optional[Project]:
        return self.projects.get(project_id)

    async def list_active_projects(self) -> list[Project]:
        return [p for p in self.projects.values() if p.is_active]

    async def sum_worked_minutes_by_month(self, user_id: str, year: int) -> dict[int, int]:
        totals: dict[int, int] = {}
        for log in self.daily_logs.values():
            if log.user_id != user_id or log.work_date.year != year:
                continue
            totals[log.work_date.month] = (
                totals.get(log.work_date.month, 0) + log.worked_minutes
            )
        return totals

    async def sum_compensation_absence_minutes(self, user_id: str, year: int) -> int:
        return self.compensation_consumed_minutes.get((user_id, year), 0)
