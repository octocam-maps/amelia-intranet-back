from datetime import date, datetime, timezone

import pytest

from src.features.time_clock.application.use_cases.create_time_clock_entry import (
    CreateTimeClockEntryUseCase,
)
from src.features.time_clock.domain.errors import InvalidTimeRangeError, TimeClockOverlapError

from .fakes import FakeTimeClockRepository


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 9, hour, minute, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_creates_entry_within_work_date():
    use_case = CreateTimeClockEntryUseCase(FakeTimeClockRepository())

    entry = await use_case.execute(
        user_id="user-1",
        work_date=date(2026, 7, 9),
        clock_in=_dt(6),
        clock_out=_dt(9),
    )

    assert entry.worked_minutes == 180


@pytest.mark.asyncio
async def test_open_entry_has_no_worked_minutes_yet():
    use_case = CreateTimeClockEntryUseCase(FakeTimeClockRepository())

    entry = await use_case.execute(
        user_id="user-1", work_date=date(2026, 7, 9), clock_in=_dt(6), clock_out=None
    )

    assert entry.worked_minutes is None


@pytest.mark.asyncio
async def test_rejects_clock_out_before_clock_in():
    use_case = CreateTimeClockEntryUseCase(FakeTimeClockRepository())

    with pytest.raises(InvalidTimeRangeError):
        await use_case.execute(
            user_id="user-1", work_date=date(2026, 7, 9), clock_in=_dt(9), clock_out=_dt(6)
        )


@pytest.mark.asyncio
async def test_rejects_entry_that_crosses_midnight():
    use_case = CreateTimeClockEntryUseCase(FakeTimeClockRepository())

    with pytest.raises(InvalidTimeRangeError):
        await use_case.execute(
            user_id="user-1",
            work_date=date(2026, 7, 8),  # distinto del día real de clock_in
            clock_in=_dt(6),
            clock_out=_dt(9),
        )


@pytest.mark.asyncio
async def test_rejects_overlapping_slot_same_day():
    repository = FakeTimeClockRepository()
    use_case = CreateTimeClockEntryUseCase(repository)
    await use_case.execute(
        user_id="user-1", work_date=date(2026, 7, 9), clock_in=_dt(6), clock_out=_dt(9)
    )

    with pytest.raises(TimeClockOverlapError):
        await use_case.execute(
            user_id="user-1", work_date=date(2026, 7, 9), clock_in=_dt(8), clock_out=_dt(12)
        )


@pytest.mark.asyncio
async def test_allows_second_non_overlapping_slot_same_day():
    """Dos tramos mañana/tarde sin solape — el hueco entre ellos es la pausa implícita."""
    repository = FakeTimeClockRepository()
    use_case = CreateTimeClockEntryUseCase(repository)
    await use_case.execute(
        user_id="user-1", work_date=date(2026, 7, 9), clock_in=_dt(6), clock_out=_dt(9)
    )

    second_entry = await use_case.execute(
        user_id="user-1", work_date=date(2026, 7, 9), clock_in=_dt(14), clock_out=_dt(18)
    )

    assert second_entry.worked_minutes == 240
    assert len(repository.entries) == 2
