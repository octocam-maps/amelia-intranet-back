from datetime import date, datetime, timedelta, timezone

import pytest

from src.features.time_clock.application.use_cases import (
    create_time_clock_entry as create_time_clock_entry_module,
)
from src.features.time_clock.application.use_cases.create_time_clock_entry import (
    CreateTimeClockEntryUseCase,
)
from src.features.time_clock.domain.entities import TimeClockSource
from src.features.time_clock.domain.errors import (
    InvalidTimeRangeError,
    ManualEntryOutOfWindowError,
    TimeClockOverlapError,
)

from .fakes import FakeTimeClockRepository

# "Hoy" (Europe/Madrid) congelado al mismo día que ya usaban los fixtures de
# este archivo (2026-07-09) — LOGIC-2 (pentest ético): el alta manual ahora
# valida `work_date` contra la fecha real del servidor, así que los tests
# congelan `today_in_madrid()` para no depender de cuándo se ejecuten.
_TODAY = date(2026, 7, 9)
_MAX_PAST_DAYS = 30


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    monkeypatch.setattr(create_time_clock_entry_module, "today_in_madrid", lambda: _TODAY)


def _build_use_case(
    repository: FakeTimeClockRepository | None = None,
    *,
    max_past_days: int = _MAX_PAST_DAYS,
) -> CreateTimeClockEntryUseCase:
    return CreateTimeClockEntryUseCase(
        repository or FakeTimeClockRepository(),
        manual_entry_max_past_days=max_past_days,
    )


def _dt(hour: int, minute: int = 0, *, day: date = _TODAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_creates_entry_within_work_date():
    use_case = _build_use_case()

    entry = await use_case.execute(
        user_id="user-1",
        work_date=_TODAY,
        clock_in=_dt(6),
        clock_out=_dt(9),
    )

    assert entry.worked_minutes == 180


@pytest.mark.asyncio
async def test_open_entry_has_no_worked_minutes_yet():
    use_case = _build_use_case()

    entry = await use_case.execute(
        user_id="user-1", work_date=_TODAY, clock_in=_dt(6), clock_out=None
    )

    assert entry.worked_minutes is None


@pytest.mark.asyncio
async def test_rejects_clock_out_before_clock_in():
    use_case = _build_use_case()

    with pytest.raises(InvalidTimeRangeError):
        await use_case.execute(
            user_id="user-1", work_date=_TODAY, clock_in=_dt(9), clock_out=_dt(6)
        )


@pytest.mark.asyncio
async def test_rejects_entry_that_crosses_midnight():
    use_case = _build_use_case()

    with pytest.raises(InvalidTimeRangeError):
        await use_case.execute(
            user_id="user-1",
            work_date=_TODAY - timedelta(days=1),  # distinto del día real de clock_in
            clock_in=_dt(6),
            clock_out=_dt(9),
        )


@pytest.mark.asyncio
async def test_rejects_overlapping_slot_same_day():
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository)
    await use_case.execute(
        user_id="user-1", work_date=_TODAY, clock_in=_dt(6), clock_out=_dt(9)
    )

    with pytest.raises(TimeClockOverlapError):
        await use_case.execute(
            user_id="user-1", work_date=_TODAY, clock_in=_dt(8), clock_out=_dt(12)
        )


@pytest.mark.asyncio
async def test_allows_second_non_overlapping_slot_same_day():
    """Dos tramos mañana/tarde sin solape — el hueco entre ellos es la pausa implícita."""
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository)
    await use_case.execute(
        user_id="user-1", work_date=_TODAY, clock_in=_dt(6), clock_out=_dt(9)
    )

    second_entry = await use_case.execute(
        user_id="user-1", work_date=_TODAY, clock_in=_dt(14), clock_out=_dt(18)
    )

    assert second_entry.worked_minutes == 240
    assert len(repository.entries) == 2


# --- LOGIC-2 (pentest ético, severidad ALTA): ventana temporal del alta
# manual. Sin este límite, cualquier interno podía fichar un tramo para
# hace 3 años o para el año que viene (`work_date` arbitrario del body). ---


@pytest.mark.asyncio
async def test_rejects_future_work_date():
    use_case = _build_use_case()
    future_day = _TODAY + timedelta(days=1)

    with pytest.raises(ManualEntryOutOfWindowError):
        await use_case.execute(
            user_id="user-1",
            work_date=future_day,
            clock_in=_dt(6, day=future_day),
            clock_out=_dt(9, day=future_day),
        )


@pytest.mark.asyncio
async def test_rejects_work_date_older_than_max_past_days():
    use_case = _build_use_case(max_past_days=30)
    too_old_day = _TODAY - timedelta(days=31)

    with pytest.raises(ManualEntryOutOfWindowError):
        await use_case.execute(
            user_id="user-1",
            work_date=too_old_day,
            clock_in=_dt(6, day=too_old_day),
            clock_out=_dt(9, day=too_old_day),
        )


@pytest.mark.asyncio
async def test_allows_work_date_exactly_at_max_past_days_boundary():
    """El límite es inclusivo: exactamente `max_past_days` atrás todavía se
    puede fichar (el pentest solo exige un límite, no lo estrecha de más)."""
    use_case = _build_use_case(max_past_days=30)
    boundary_day = _TODAY - timedelta(days=30)

    entry = await use_case.execute(
        user_id="user-1",
        work_date=boundary_day,
        clock_in=_dt(6, day=boundary_day),
        clock_out=_dt(9, day=boundary_day),
    )

    assert entry.work_date == boundary_day


@pytest.mark.asyncio
async def test_allows_work_date_equal_to_today():
    use_case = _build_use_case()

    entry = await use_case.execute(
        user_id="user-1", work_date=_TODAY, clock_in=_dt(6), clock_out=_dt(9)
    )

    assert entry.work_date == _TODAY


@pytest.mark.asyncio
async def test_window_is_tunable_via_constructor():
    """RRHH puede ajustar la ventana sin tocar lógica (constante inyectada
    desde `Settings`, no hardcodeada en el caso de uso)."""
    use_case = _build_use_case(max_past_days=5)
    six_days_ago = _TODAY - timedelta(days=6)

    with pytest.raises(ManualEntryOutOfWindowError):
        await use_case.execute(
            user_id="user-1",
            work_date=six_days_ago,
            clock_in=_dt(6, day=six_days_ago),
            clock_out=_dt(9, day=six_days_ago),
        )


# --- LOGIC-2: `source` diferenciado — el alta manual siempre persiste
# "manual", nunca "web" (el default histórico compartido con el fichaje en
# vivo, que RRHH no podía distinguir en el export). ---


@pytest.mark.asyncio
async def test_manual_entry_always_persists_source_manual():
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository)

    entry = await use_case.execute(
        user_id="user-1", work_date=_TODAY, clock_in=_dt(6), clock_out=_dt(9)
    )

    assert entry.source == TimeClockSource.MANUAL
    assert repository.entries[entry.id].source == "manual"
