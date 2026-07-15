"""Fake en memoria de `ITimeClockRepository` — permite testear los casos de
uso sin Postgres, igual que `features/auth/application/tests/fakes.py`."""

import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Optional

from src.features.time_clock.domain.entities import (
    TimeClockBreak,
    TimeClockEntry,
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
    ):
        self.entries = {e.id: e for e in (entries or [])}
        self.breaks: dict[str, TimeClockBreak] = {b.id: b for b in (breaks or [])}
        # Identidad/contacto para `list_export_rows_for_all` — el fake no
        # tiene una tabla `users`/`user_profiles` real, así que se pasan por
        # fuera solo cuando un test necesita el informe XLSX.
        self.full_names: dict[str, str] = full_names or {}
        self.dni_by_user: dict[str, str] = dni_by_user or {}
        self.phone_by_user: dict[str, str] = phone_by_user or {}

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

    async def list_entries_for_user(
        self, user_id: str, *, date_from: date, date_to: date
    ) -> list[TimeClockEntry]:
        return [
            e
            for e in self.entries.values()
            if e.user_id == user_id and date_from <= e.work_date <= date_to
        ]

    async def list_entries_for_all(self, *, date_from: date, date_to: date) -> list[TimeClockEntry]:
        return [e for e in self.entries.values() if date_from <= e.work_date <= date_to]

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
            )
            for e in self.entries.values()
            if date_from <= e.work_date <= date_to
        ]

    async def find_overlapping_entry(
        self, user_id, work_date, clock_in, clock_out, *, exclude_entry_id=None
    ) -> Optional[TimeClockEntry]:
        effective_end = clock_out or datetime.max.replace(tzinfo=clock_in.tzinfo)
        for entry in self.entries.values():
            if entry.id == exclude_entry_id:
                continue
            if entry.user_id != user_id or entry.work_date != work_date:
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
