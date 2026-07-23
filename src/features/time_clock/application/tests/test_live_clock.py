"""
Fichaje en vivo (modelo "ambos", docs/deck-fase3/01-home-empleado.png):
fichar entrada/salida y pausar/reanudar el tramo abierto, más el contador
"Esta semana Xh/40h".
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.features.time_clock.application.use_cases.clock_in import ClockInUseCase
from src.features.time_clock.application.use_cases.clock_out import ClockOutUseCase
from src.features.time_clock.application.use_cases.end_break import EndBreakUseCase
from src.features.time_clock.application.use_cases.get_live_status import GetLiveStatusUseCase
from src.features.time_clock.application.use_cases.start_break import StartBreakUseCase
from src.features.time_clock.domain.entities import TimeClockEntry
from src.features.time_clock.domain.errors import (
    TimeClockAlreadyClockedInError,
    TimeClockBreakAlreadyOpenError,
    TimeClockNoOpenBreakError,
    TimeClockNoOpenEntryError,
)

from .fakes import FakeTimeClockRepository


@pytest.mark.asyncio
async def test_clock_in_opens_a_new_entry():
    repository = FakeTimeClockRepository()
    use_case = ClockInUseCase(repository)

    entry = await use_case.execute(user_id="user-1")

    assert entry.clock_out is None
    assert repository.entries[entry.id].user_id == "user-1"


@pytest.mark.asyncio
async def test_clock_in_persists_source_live():
    """LOGIC-2 (pentest ético): el fichaje en vivo debe distinguirse del alta
    manual en `source` — antes ambos escribían "web" y RRHH no podía saber
    qué horas eran autodeclaradas."""
    from src.features.time_clock.domain.entities import TimeClockSource

    repository = FakeTimeClockRepository()
    use_case = ClockInUseCase(repository)

    entry = await use_case.execute(user_id="user-1")

    assert entry.source == TimeClockSource.LIVE
    assert repository.entries[entry.id].source == "live"


@pytest.mark.asyncio
async def test_clock_in_rejects_if_already_clocked_in():
    open_entry = TimeClockEntry(
        id="entry-1",
        user_id="user-1",
        work_date=date(2026, 7, 9),
        clock_in=datetime.now(timezone.utc),
        clock_out=None,
        source="web",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repository = FakeTimeClockRepository(entries=[open_entry])
    use_case = ClockInUseCase(repository)

    with pytest.raises(TimeClockAlreadyClockedInError):
        await use_case.execute(user_id="user-1")


@pytest.mark.asyncio
async def test_clock_out_rejects_when_nothing_open():
    repository = FakeTimeClockRepository()
    use_case = ClockOutUseCase(repository)

    with pytest.raises(TimeClockNoOpenEntryError):
        await use_case.execute(user_id="user-1")


@pytest.mark.asyncio
async def test_clock_out_closes_the_open_entry_and_any_open_break():
    now = datetime.now(timezone.utc)
    open_entry = TimeClockEntry(
        id="entry-1",
        user_id="user-1",
        work_date=now.date(),
        clock_in=now - timedelta(hours=2),
        clock_out=None,
        source="web",
        created_at=now,
        updated_at=now,
    )
    repository = FakeTimeClockRepository(entries=[open_entry])
    await StartBreakUseCase(repository).execute(user_id="user-1")

    closed_entry = await ClockOutUseCase(repository).execute(user_id="user-1")

    assert closed_entry.clock_out is not None
    open_break = await repository.find_open_break_for_entry("entry-1")
    assert open_break is None  # la pausa se cerró junto con la salida


@pytest.mark.asyncio
async def test_start_break_rejects_without_open_entry():
    repository = FakeTimeClockRepository()

    with pytest.raises(TimeClockNoOpenEntryError):
        await StartBreakUseCase(repository).execute(user_id="user-1")


@pytest.mark.asyncio
async def test_start_break_rejects_if_already_on_break():
    now = datetime.now(timezone.utc)
    open_entry = TimeClockEntry(
        id="entry-1",
        user_id="user-1",
        work_date=now.date(),
        clock_in=now - timedelta(hours=1),
        clock_out=None,
        source="web",
        created_at=now,
        updated_at=now,
    )
    repository = FakeTimeClockRepository(entries=[open_entry])
    await StartBreakUseCase(repository).execute(user_id="user-1")

    with pytest.raises(TimeClockBreakAlreadyOpenError):
        await StartBreakUseCase(repository).execute(user_id="user-1")


@pytest.mark.asyncio
async def test_end_break_rejects_without_open_break():
    now = datetime.now(timezone.utc)
    open_entry = TimeClockEntry(
        id="entry-1",
        user_id="user-1",
        work_date=now.date(),
        clock_in=now - timedelta(hours=1),
        clock_out=None,
        source="web",
        created_at=now,
        updated_at=now,
    )
    repository = FakeTimeClockRepository(entries=[open_entry])

    with pytest.raises(TimeClockNoOpenBreakError):
        await EndBreakUseCase(repository).execute(user_id="user-1")


@pytest.mark.asyncio
async def test_live_status_reflects_open_entry_and_break():
    now = datetime.now(timezone.utc)
    open_entry = TimeClockEntry(
        id="entry-1",
        user_id="user-1",
        work_date=now.date(),
        clock_in=now - timedelta(hours=1),
        clock_out=None,
        source="web",
        created_at=now,
        updated_at=now,
    )
    repository = FakeTimeClockRepository(entries=[open_entry])
    await StartBreakUseCase(repository).execute(user_id="user-1")

    status = await GetLiveStatusUseCase(repository).execute(user_id="user-1")

    assert status.open_entry is not None
    assert status.open_entry.id == "entry-1"
    assert status.open_entry.on_break is True
    assert status.expected_weekly_minutes == 40 * 60


@pytest.mark.asyncio
async def test_live_status_with_no_entries_is_idle():
    repository = FakeTimeClockRepository()

    status = await GetLiveStatusUseCase(repository).execute(user_id="user-1")

    assert status.open_entry is None
    assert status.week_worked_minutes == 0
