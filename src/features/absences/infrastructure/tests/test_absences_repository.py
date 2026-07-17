"""
Regresión: `/absences/requests/pending` y `/requests/all` deben devolver
`user_full_name` (JOIN con `users`) para que la bandeja de aprobación y el
gantt "Calendario de la plantilla" muestren el nombre real en vez de
"Empleado #XXXX". Mismo patrón de mock de pool que
`features/time_clock/infrastructure/tests/test_time_clock_repository.py`.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.absences.infrastructure.repositories.absence_repository import (
    PostgresAbsenceRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "req-1",
        "user_id": "user-1",
        "absence_type_id": "type-vacaciones",
        "start_date": date(2026, 7, 20),
        "end_date": date(2026, 7, 24),
        "days_count": 5,
        "reason": None,
        "status": "pending",
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
        "created_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_pending_requests_enriches_with_user_full_name():
    pool = AsyncMock()
    pool.fetch.return_value = [_row(user_full_name="Ana García")]
    repository = PostgresAbsenceRepository(pool)

    requests = await repository.list_pending_requests()

    assert requests[0].user_full_name == "Ana García"
    query = pool.fetch.call_args[0][0]
    assert "JOIN users" in query
    assert "status = 'pending'" in query


@pytest.mark.asyncio
async def test_list_all_requests_enriches_with_user_full_name():
    pool = AsyncMock()
    pool.fetch.return_value = [_row(user_full_name="Ana García")]
    repository = PostgresAbsenceRepository(pool)

    requests = await repository.list_all_requests()

    assert requests[0].user_full_name == "Ana García"


def _type_row(**overrides) -> dict:
    row = {
        "id": "type-1",
        "code": "excedencia",
        "name": "Excedencia",
        "is_paid": False,
        "affects_balance": False,
        "default_entitled_days": 0,
        "color": None,
        "is_active": True,
        "requires_approval": True,
        "requires_justification": False,
        "max_days_per_year": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_all_types_does_not_filter_by_is_active():
    """A diferencia de `list_types` (empleado, solo activos), la vista de
    gestión del admin debe traer también los desactivados."""
    pool = AsyncMock()
    pool.fetch.return_value = [_type_row(is_active=False)]
    repository = PostgresAbsenceRepository(pool)

    types = await repository.list_all_types()

    query = pool.fetch.call_args[0][0]
    assert "is_active" not in query
    assert types[0].is_active is False


@pytest.mark.asyncio
async def test_update_type_returns_none_when_not_found():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresAbsenceRepository(pool)

    result = await repository.update_type(
        "missing-id",
        name=None,
        is_paid=None,
        affects_balance=None,
        default_entitled_days=None,
        color=None,
        is_active=False,
    )

    assert result is None


@pytest.mark.asyncio
async def test_list_requests_for_user_leaves_user_full_name_none():
    """`SELECT *` sin JOIN — sin `user_full_name` en la fila, no debe reventar."""
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresAbsenceRepository(pool)

    requests = await repository.list_requests_for_user("user-1")

    assert requests[0].user_full_name is None


@pytest.mark.asyncio
async def test_try_consume_balance_writes_to_used_days_not_pending_days():
    """Autoaprobación del administrador (B-1c): a diferencia de
    `try_reserve_balance` (escribe `pending_days`), esta query debe tocar
    `used_days` directamente — mismo contrato atómico anti-overdraft
    (RACE-1)."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"id": "balance-1"}
    repository = PostgresAbsenceRepository(pool)

    consumed = await repository.try_consume_balance(
        "admin-1", "type-vacaciones", 2026, used_delta=5.0
    )

    assert consumed is True
    query, *params = pool.fetchrow.call_args[0]
    assert "used_days = used_days + $4" in query
    assert "pending_days" not in query.split("SET")[1].split("WHERE")[0]
    assert params == ["admin-1", "type-vacaciones", 2026, 5.0]


@pytest.mark.asyncio
async def test_try_consume_balance_returns_false_when_balance_is_insufficient():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresAbsenceRepository(pool)

    consumed = await repository.try_consume_balance(
        "admin-1", "type-vacaciones", 2026, used_delta=5.0
    )

    assert consumed is False


@pytest.mark.asyncio
async def test_create_approved_request_inserts_with_approved_status_and_self_review():
    """La solicitud del admin nace ya `approved`, con `reviewed_by` apuntando
    al propio solicitante y `reviewed_at` informado — nunca pasa por
    `pending`."""
    pool = AsyncMock()
    pool.fetchrow.return_value = _row(
        status="approved", reviewed_by="admin-1", review_note="Autoaprobado"
    )
    repository = PostgresAbsenceRepository(pool)

    request = await repository.create_approved_request(
        user_id="admin-1",
        absence_type_id="type-vacaciones",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 24),
        days_count=5.0,
        reason=None,
        review_note="Autoaprobado",
    )

    assert request.status == "approved"
    assert request.reviewed_by == "admin-1"
    query, *params = pool.fetchrow.call_args[0]
    assert "'approved'" in query
    assert "reviewed_by" in query
    assert params == [
        "admin-1",
        "type-vacaciones",
        date(2026, 7, 20),
        date(2026, 7, 24),
        5.0,
        None,
        "Autoaprobado",
    ]


@pytest.mark.asyncio
async def test_list_overlapping_requests_filters_by_user_status_and_date_range():
    """Anti-solape (bug real, auditoría QA): solo `pending`/`approved` del
    mismo usuario, con el solape estándar de rangos en la propia query."""
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresAbsenceRepository(pool)

    requests = await repository.list_overlapping_requests(
        "user-1", start_date=date(2026, 7, 22), end_date=date(2026, 7, 26)
    )

    assert requests[0].id == "req-1"
    query, *params = pool.fetch.call_args[0]
    assert "status IN ('pending', 'approved')" in query
    assert "start_date <= $3" in query
    assert "end_date >= $2" in query
    assert params == ["user-1", date(2026, 7, 22), date(2026, 7, 26)]


def _calendar_row(**overrides) -> dict:
    row = {
        "request_id": "req-1",
        "user_id": "user-1",
        "user_full_name": "Ana García",
        "absence_type_id": "type-vacaciones",
        "absence_type_name": "Vacaciones",
        "absence_type_color": "#00D170",
        "start_date": date(2026, 7, 20),
        "end_date": date(2026, 7, 24),
        "days_count": 5,
        "status": "approved",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_calendar_entries_joins_users_and_absence_types():
    """LOTE 4 — "Calendario general de la plantilla": la query debe traer
    `user_full_name` y `absence_type_name`/`absence_type_color` ya
    resueltos (JOIN), filtrar solo `pending`/`approved` y solapar contra
    el rango dado."""
    pool = AsyncMock()
    pool.fetch.return_value = [_calendar_row()]
    repository = PostgresAbsenceRepository(pool)

    entries = await repository.list_calendar_entries(
        date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry.request_id == "req-1"
    assert entry.user_full_name == "Ana García"
    assert entry.absence_type_name == "Vacaciones"
    assert entry.absence_type_color == "#00D170"
    assert entry.days_count == 5.0

    query, *params = pool.fetch.call_args[0]
    assert "JOIN users" in query
    assert "JOIN absence_types" in query
    assert "status IN ('pending', 'approved')" in query
    assert "start_date <= $2" in query
    assert "end_date >= $1" in query
    assert params == [date(2026, 7, 1), date(2026, 7, 31)]
