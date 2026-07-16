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

    page = await use_case.execute(
        requester_id="user-1",
        requester_role="empleado",
        target_user_id=None,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert [e.id for e in page.items] == ["e1"]
    assert page.total == 1


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

    page = await use_case.execute(
        requester_id="admin-1",
        requester_role="administrador",
        target_user_id=None,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert {e.id for e in page.items} == {"e1", "e2"}
    assert page.total == 2


@pytest.mark.asyncio
async def test_admin_can_filter_by_target_user_id():
    """X2 (Lote 1): el admin SÍ puede pedir el fichaje de una persona
    concreta desde la vista "toda la plantilla" — el backend ya lo permitía,
    el lote solo añade el selector en el frontend."""
    repository = FakeTimeClockRepository(
        [
            _entry("e1", "user-1", date(2026, 7, 9)),
            _entry("e2", "user-2", date(2026, 7, 9)),
        ]
    )
    use_case = ListTimeClockEntriesUseCase(repository)

    page = await use_case.execute(
        requester_id="admin-1",
        requester_role="administrador",
        target_user_id="user-2",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert [e.id for e in page.items] == ["e2"]
    assert page.total == 1


@pytest.mark.asyncio
async def test_list_includes_full_name_from_repository_join():
    """X-BUG (Lote 1): la columna "Empleado" mostraba el UUID — el listado
    debe traer `full_name` ya resuelto (el fake simula el mismo JOIN a
    `users` que hace el repositorio real)."""
    repository = FakeTimeClockRepository(
        [_entry("e1", "user-1", date(2026, 7, 9))],
        full_names={"user-1": "Ana García"},
    )
    use_case = ListTimeClockEntriesUseCase(repository)

    page = await use_case.execute(
        requester_id="user-1",
        requester_role="empleado",
        target_user_id=None,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert page.items[0].full_name == "Ana García"


@pytest.mark.asyncio
async def test_pagination_respects_limit_and_offset_and_reports_total():
    """X1 (Lote 1): con ~850 tramos/mes, el listado tiene que paginar.
    `total` cuenta TODO el rango, sin recortar por `limit`/`offset`."""
    entries = [_entry(f"e{i}", "user-1", date(2026, 7, 1 + i)) for i in range(5)]
    repository = FakeTimeClockRepository(entries)
    use_case = ListTimeClockEntriesUseCase(repository)

    page = await use_case.execute(
        requester_id="user-1",
        requester_role="empleado",
        target_user_id=None,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        limit=2,
        offset=2,
    )

    assert len(page.items) == 2
    assert page.total == 5


@pytest.mark.asyncio
async def test_admin_can_filter_by_multiple_target_user_ids():
    """Multi-selector de personas (Lote 2): el admin puede acotar la vista
    aumentada a varias personas a la vez, no solo a una."""
    repository = FakeTimeClockRepository(
        [
            _entry("e1", "user-1", date(2026, 7, 9)),
            _entry("e2", "user-2", date(2026, 7, 9)),
            _entry("e3", "user-3", date(2026, 7, 9)),
        ]
    )
    use_case = ListTimeClockEntriesUseCase(repository)

    page = await use_case.execute(
        requester_id="admin-1",
        requester_role="administrador",
        target_user_ids=["user-1", "user-3"],
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert {e.id for e in page.items} == {"e1", "e3"}
    assert page.total == 2


@pytest.mark.asyncio
async def test_employee_cannot_query_multiple_target_user_ids():
    """RGPD: un no-admin no puede colarse a la vista multi-persona ni
    aunque uno de los ids sea el suyo — solo puede pedir su propio id, solo."""
    use_case = ListTimeClockEntriesUseCase(FakeTimeClockRepository())

    with pytest.raises(TimeClockForbiddenError):
        await use_case.execute(
            requester_id="user-1",
            requester_role="empleado",
            target_user_ids=["user-1", "user-2"],
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 31),
        )


@pytest.mark.asyncio
async def test_employee_can_still_query_their_own_id_via_target_user_ids():
    """El mismo guard no debe bloquear el caso trivial: un no-admin pidiendo
    su propio id dentro de `target_user_ids` (p.ej. un cliente que siempre
    manda la lista, nunca el singular) sigue permitido."""
    repository = FakeTimeClockRepository([_entry("e1", "user-1", date(2026, 7, 9))])
    use_case = ListTimeClockEntriesUseCase(repository)

    page = await use_case.execute(
        requester_id="user-1",
        requester_role="empleado",
        target_user_ids=["user-1"],
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert [e.id for e in page.items] == ["e1"]


@pytest.mark.asyncio
async def test_no_limit_returns_full_range_unpaginated():
    """El export CSV (`GET /entries/export`) llama al mismo caso de uso con
    `limit=None` — debe devolver TODO el rango, no una página."""
    entries = [_entry(f"e{i}", "user-1", date(2026, 7, 1 + i)) for i in range(5)]
    repository = FakeTimeClockRepository(entries)
    use_case = ListTimeClockEntriesUseCase(repository)

    page = await use_case.execute(
        requester_id="user-1",
        requester_role="empleado",
        target_user_id=None,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        limit=None,
        offset=0,
    )

    assert len(page.items) == 5
    assert page.total == 5
