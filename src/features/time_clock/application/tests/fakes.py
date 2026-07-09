"""Fake en memoria de `ITimeClockRepository` — permite testear los casos de
uso sin Postgres, igual que `features/auth/application/tests/fakes.py`."""

import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Optional

from src.features.time_clock.domain.entities import TimeClockEntry


@dataclass
class FakeTimeClockRepository:
    entries: dict[str, TimeClockEntry]

    def __init__(self, entries: Optional[list[TimeClockEntry]] = None):
        self.entries = {e.id: e for e in (entries or [])}

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
