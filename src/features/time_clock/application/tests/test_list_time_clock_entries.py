from datetime import date, datetime, timezone

import pytest

from src.features.time_clock.application.use_cases.list_time_clock_entries import (
    ListTimeClockEntriesUseCase,
)
from src.features.time_clock.domain.entities import TimeClockEntry
from src.features.time_clock.domain.errors import TimeClockForbiddenError

from .fakes import FakeTimeClockRepository


def _entry(entry_id: str, user_id: str, day: date) -> TimeClockEntry:
    now = datetime(2026, 7, 9, 6, tzinfo=timezone.utc)
    return TimeClockEntry(
        id=entry_id,
        user_id=user_id,
        work_date=day,
        clock_in=now,
        clock_out=now,
        source="web",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_employee_only_sees_their_own_entries():
    repository = FakeTimeClockRepository(
        [
            _entry("e1", "user-1", date(2026, 7, 9)),
            _entry("e2", "user-2", date(2026, 7, 9)),
        ]
    )
    use_case = ListTimeClockEntriesUseCase(repository)

    entries = await use_case.execute(
        requester_id="user-1",
        requester_role="empleado",
        target_user_id=None,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert [e.id for e in entries] == ["e1"]


@pytest.mark.asyncio
async def test_employee_cannot_query_another_user():
    use_case = ListTimeClockEntriesUseCase(FakeTimeClockRepository())

    with pytest.raises(TimeClockForbiddenError):
        await use_case.execute(
            requester_id="user-1",
            requester_role="empleado",
            target_user_id="user-2",
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 31),
        )


@pytest.mark.asyncio
async def test_admin_without_target_sees_all_entries():
    repository = FakeTimeClockRepository(
        [
            _entry("e1", "user-1", date(2026, 7, 9)),
            _entry("e2", "user-2", date(2026, 7, 9)),
        ]
    )
    use_case = ListTimeClockEntriesUseCase(repository)

    entries = await use_case.execute(
        requester_id="admin-1",
        requester_role="administrador",
        target_user_id=None,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert {e.id for e in entries} == {"e1", "e2"}
