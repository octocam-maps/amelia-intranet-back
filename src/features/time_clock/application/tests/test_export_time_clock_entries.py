from datetime import date, datetime, timezone

import pytest

from src.features.time_clock.application.use_cases.export_time_clock_entries import (
    ExportTimeClockEntriesUseCase,
)
from src.features.time_clock.domain.entities import TimeClockEntry

from .fakes import FakeTimeClockRepository


def _entry(entry_id: str, user_id: str, day: date, with_clock_out: bool = True) -> TimeClockEntry:
    clock_in = datetime(2026, 7, 9, 8, tzinfo=timezone.utc)
    clock_out = datetime(2026, 7, 9, 12, tzinfo=timezone.utc) if with_clock_out else None
    return TimeClockEntry(
        id=entry_id,
        user_id=user_id,
        work_date=day,
        clock_in=clock_in,
        clock_out=clock_out,
        source="web",
        created_at=clock_in,
        updated_at=clock_in,
    )


@pytest.mark.asyncio
async def test_export_returns_rows_for_all_users_in_range():
    repository = FakeTimeClockRepository(
        entries=[
            _entry("e1", "user-1", date(2026, 7, 9)),
            _entry("e2", "user-2", date(2026, 7, 9)),
            _entry("e3", "user-1", date(2026, 6, 1)),  # fuera de rango
        ],
        full_names={"user-1": "Ana García", "user-2": "Luis Pérez Ruiz"},
        dni_by_user={"user-1": "12345678A"},
        phone_by_user={"user-1": "600111222"},
    )
    use_case = ExportTimeClockEntriesUseCase(repository)

    rows = await use_case.execute(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))

    assert {row.user_id for row in rows} == {"user-1", "user-2"}
    ana = next(row for row in rows if row.user_id == "user-1")
    assert ana.full_name == "Ana García"
    assert ana.dni_nif == "12345678A"
    assert ana.phone == "600111222"
    assert ana.worked_minutes == 240


@pytest.mark.asyncio
async def test_export_open_entry_has_no_worked_minutes():
    repository = FakeTimeClockRepository(
        entries=[_entry("e1", "user-1", date(2026, 7, 9), with_clock_out=False)],
        full_names={"user-1": "Ana García"},
    )
    use_case = ExportTimeClockEntriesUseCase(repository)

    rows = await use_case.execute(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))

    assert rows[0].clock_out is None
    assert rows[0].worked_minutes is None
