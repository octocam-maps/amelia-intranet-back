from datetime import date, datetime, timezone

import pytest

from src.features.time_clock.application.use_cases.delete_time_clock_entry import (
    DeleteTimeClockEntryUseCase,
)
from src.features.time_clock.application.use_cases.update_time_clock_entry import (
    UpdateTimeClockEntryUseCase,
)
from src.features.time_clock.domain.entities import TimeClockEntry
from src.features.time_clock.domain.errors import TimeClockForbiddenError

from .fakes import FakeTimeClockRepository


def _open_entry() -> TimeClockEntry:
    now = datetime(2026, 7, 9, 6, tzinfo=timezone.utc)
    return TimeClockEntry(
        id="entry-1",
        user_id="user-1",
        work_date=date(2026, 7, 9),
        clock_in=now,
        clock_out=None,
        source="web",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_owner_can_close_their_open_entry():
    repository = FakeTimeClockRepository([_open_entry()])
    use_case = UpdateTimeClockEntryUseCase(repository)

    updated = await use_case.execute(
        entry_id="entry-1",
        requester_id="user-1",
        requester_role="empleado",
        clock_in=datetime(2026, 7, 9, 6, tzinfo=timezone.utc),
        clock_out=datetime(2026, 7, 9, 14, tzinfo=timezone.utc),
    )

    assert updated.worked_minutes == 480


@pytest.mark.asyncio
async def test_other_employee_cannot_edit_entry():
    repository = FakeTimeClockRepository([_open_entry()])
    use_case = UpdateTimeClockEntryUseCase(repository)

    with pytest.raises(TimeClockForbiddenError):
        await use_case.execute(
            entry_id="entry-1",
            requester_id="user-2",
            requester_role="empleado",
            clock_in=datetime(2026, 7, 9, 6, tzinfo=timezone.utc),
            clock_out=datetime(2026, 7, 9, 14, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_admin_can_edit_anyones_entry():
    repository = FakeTimeClockRepository([_open_entry()])
    use_case = UpdateTimeClockEntryUseCase(repository)

    updated = await use_case.execute(
        entry_id="entry-1",
        requester_id="admin-1",
        requester_role="administrador",
        clock_in=datetime(2026, 7, 9, 6, tzinfo=timezone.utc),
        clock_out=datetime(2026, 7, 9, 10, tzinfo=timezone.utc),
    )

    assert updated.worked_minutes == 240


@pytest.mark.asyncio
async def test_owner_can_delete_their_entry():
    repository = FakeTimeClockRepository([_open_entry()])
    use_case = DeleteTimeClockEntryUseCase(repository)

    await use_case.execute(entry_id="entry-1", requester_id="user-1", requester_role="empleado")

    assert await repository.find_entry_by_id("entry-1") is None


@pytest.mark.asyncio
async def test_other_employee_cannot_delete_entry():
    repository = FakeTimeClockRepository([_open_entry()])
    use_case = DeleteTimeClockEntryUseCase(repository)

    with pytest.raises(TimeClockForbiddenError):
        await use_case.execute(entry_id="entry-1", requester_id="user-2", requester_role="empleado")
