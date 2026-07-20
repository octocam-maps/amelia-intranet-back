"""
Tests del adaptador asyncpg de `staff` con el pool mockeado (mismo patrón
que `features/absences/infrastructure/tests/test_absences_repository.py`).
`create_staff_member`/`update_staff_member` usan `db.acquire()` +
`connection.transaction()` (igual que `auth.user_repository`), así que se
mockean con un pool/conexión falsos que respetan el mismo protocolo async
context manager que `asyncpg`.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.staff.infrastructure.repositories.staff_repository import (
    PostgresStaffRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "user-1",
        "full_name": "Sandra Ramírez",
        "email": "sandra@ameliahub.com",
        "avatar_url": None,
        "job_title": "Project Manager",
        "status": "invited",
        "hire_date": None,
        "created_at": datetime.now(timezone.utc),
        "department_id": None,
        "department_name": None,
        "entity_id": "entity-hub",
        "entity_code": "hub",
        "role_id": "role-empleado",
        "role_code": "empleado",
        "vacation_days_per_year": 23,
        "vacation_days_override": 23,
    }
    row.update(overrides)
    return row


class _NullContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _AcquireContext:
    def __init__(self, connection):
        self._connection = connection

    async def __aenter__(self):
        return self._connection

    async def __aexit__(self, *args):
        return False


class _FakeConnection:
    """Espeja `asyncpg.Connection`: `fetchval`/`fetchrow`/`execute` async, y
    `transaction()` como context manager que no hace nada real (el
    aislamiento de una transacción de verdad no es lo que se está
    probando aquí, sino que el repositorio llama a las queries correctas)."""

    def __init__(self):
        self.fetchval = AsyncMock()
        self.fetchrow = AsyncMock()
        self.execute = AsyncMock()

    def transaction(self):
        return _NullContext()


class _FakePool:
    """Espeja `DatabasePool`: además de `acquire()` (usado dentro de la
    transacción), expone `fetch`/`fetchrow`/`fetchval` de nivel superior —
    los usa `find_by_id` al recargar la entidad tras el INSERT/UPDATE."""

    def __init__(self, connection: _FakeConnection):
        self.connection = connection
        self.fetch = AsyncMock()
        self.fetchrow = AsyncMock()
        self.fetchval = AsyncMock()

    def acquire(self):
        return _AcquireContext(self.connection)


@pytest.mark.asyncio
async def test_list_staff_filters_by_entity_and_search_with_pagination():
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresStaffRepository(pool)

    await repository.list_staff(entity_code="hub", search="sandra", page=2, page_size=10)

    query, *args = pool.fetch.call_args[0]
    assert "e.code = $1" in query
    assert "u.full_name ILIKE $2" in query
    assert "LIMIT $3 OFFSET $4" in query
    assert args == ["hub", "%sandra%", 10, 10]


@pytest.mark.asyncio
async def test_resolve_entity_id_returns_none_for_unknown_code():
    pool = AsyncMock()
    pool.fetchval.return_value = None
    repository = PostgresStaffRepository(pool)

    assert await repository.resolve_entity_id("not-a-real-entity") is None


@pytest.mark.asyncio
async def test_get_or_create_department_id_upserts_on_conflict():
    pool = AsyncMock()
    pool.fetchrow.return_value = {"id": "dept-1"}
    repository = PostgresStaffRepository(pool)

    department_id = await repository.get_or_create_department_id(
        entity_id="entity-hub", department_name="Operaciones"
    )

    assert department_id == "dept-1"
    query = pool.fetchrow.call_args[0][0]
    assert "ON CONFLICT (entity_id, name)" in query


@pytest.mark.asyncio
async def test_create_staff_member_inserts_user_and_initial_vacation_balance():
    connection = _FakeConnection()
    connection.fetchval.return_value = "user-1"
    pool = _FakePool(connection)
    pool.fetchrow.return_value = _row()
    repository = PostgresStaffRepository(pool)
    expires_at = datetime(2026, 7, 24, tzinfo=timezone.utc)

    member = await repository.create_staff_member(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title="Project Manager",
        department_id=None,
        entity_id="entity-hub",
        role_id="role-empleado",
        is_external=False,
        hire_date=None,
        vacation_days_override=23,
        invited_by="admin-1",
        expires_at=expires_at,
    )

    assert member.id == "user-1"
    insert_query = connection.fetchval.call_args[0][0]
    assert "INSERT INTO users" in insert_query
    assert "'invited'" in insert_query
    # Se sembró el saldo inicial (override=23) Y la fila de `invitations`,
    # en la MISMA transacción que `users`.
    assert connection.execute.await_count == 2
    balance_query, *balance_args = connection.execute.call_args_list[0][0]
    assert "absence_balances" in balance_query
    assert balance_args == ["user-1", 23]
    invitation_query, *invitation_args = connection.execute.call_args_list[1][0]
    assert "INSERT INTO invitations" in invitation_query
    assert invitation_args[0] == "sandra@ameliahub.com"
    assert invitation_args[1] == "role-empleado"
    assert invitation_args[2] == "entity-hub"
    assert invitation_args[4] == "admin-1"  # invited_by
    assert invitation_args[5] == expires_at


@pytest.mark.asyncio
async def test_create_staff_member_seeds_balance_from_automatic_calculation_when_no_override():
    """Regresión del cálculo automático: sin override, el saldo inicial se
    siembra SIEMPRE (no solo cuando el admin escribe un número) usando
    `calculate_vacation_entitlement_days(hire_date, year)`."""
    connection = _FakeConnection()
    connection.fetchval.return_value = "user-1"
    pool = _FakePool(connection)
    pool.fetchrow.return_value = _row()
    repository = PostgresStaffRepository(pool)

    await repository.create_staff_member(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title=None,
        department_id=None,
        entity_id="entity-hub",
        role_id="role-empleado",
        is_external=False,
        hire_date=date(2020, 1, 1),  # año completo -> 20 días calculados
        vacation_days_override=None,
        invited_by="admin-1",
        expires_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )

    # Saldo (calculado) + invitación — nunca se salta el saldo.
    assert connection.execute.await_count == 2
    balance_query, *balance_args = connection.execute.call_args_list[0][0]
    assert "absence_balances" in balance_query
    assert balance_args == ["user-1", 20.0]


@pytest.mark.asyncio
async def test_update_staff_member_returns_none_when_not_found():
    connection = _FakeConnection()
    connection.fetchrow.return_value = None
    pool = _FakePool(connection)
    repository = PostgresStaffRepository(pool)

    result = await repository.update_staff_member(
        "missing-id",
        job_title="Nuevo puesto",
        department_id=None,
        entity_id=None,
        role_id=None,
        is_external=None,
        vacation_days_override=None,
        clear_vacation_days_override=False,
        status=None,
    )

    assert result is None
    pool.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_staff_member_deactivating_sets_status_suspended():
    connection = _FakeConnection()
    connection.fetchrow.return_value = {
        "id": "user-1",
        "hire_date": None,
        "vacation_days_override": 23,
    }
    pool = _FakePool(connection)
    pool.fetchrow.return_value = _row(status="suspended")
    repository = PostgresStaffRepository(pool)

    updated = await repository.update_staff_member(
        "user-1",
        job_title=None,
        department_id=None,
        entity_id=None,
        role_id=None,
        is_external=None,
        vacation_days_override=None,
        clear_vacation_days_override=False,
        status="suspended",
    )

    assert updated.status == "suspended"
    update_query, *update_args = connection.fetchrow.call_args[0]
    assert "COALESCE($7, status)" in update_query
    assert "vacation_days_override = CASE" in update_query
    assert update_args[6] == "suspended"
    # No se tocó el override en esta petición -> no se recalcula el saldo.
    connection.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_staff_member_not_touching_override_does_not_recompute_balance():
    """Editar un campo no relacionado (p. ej. el puesto) no debe reescribir
    `absence_balances` de rebote — solo se recalcula cuando el override
    realmente se fija o se vacía esta petición."""
    connection = _FakeConnection()
    connection.fetchrow.return_value = {
        "id": "user-1",
        "hire_date": date(2020, 1, 1),
        "vacation_days_override": None,
    }
    pool = _FakePool(connection)
    pool.fetchrow.return_value = _row()
    repository = PostgresStaffRepository(pool)

    await repository.update_staff_member(
        "user-1",
        job_title="Nuevo puesto",
        department_id=None,
        entity_id=None,
        role_id=None,
        is_external=None,
        vacation_days_override=None,
        clear_vacation_days_override=False,
        status=None,
    )

    connection.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_staff_member_clearing_override_recomputes_from_hire_date():
    """`clear_vacation_days_override=True` (el admin vació el campo en el
    formulario) fuerza `vacation_days_override = NULL` y recalcula el saldo
    desde `hire_date` — vuelve a automático."""
    connection = _FakeConnection()
    connection.fetchrow.return_value = {
        "id": "user-1",
        "hire_date": date(2020, 1, 1),  # calcularía 20
        "vacation_days_override": None,
    }
    pool = _FakePool(connection)
    pool.fetchrow.return_value = _row()
    repository = PostgresStaffRepository(pool)

    await repository.update_staff_member(
        "user-1",
        job_title=None,
        department_id=None,
        entity_id=None,
        role_id=None,
        is_external=None,
        vacation_days_override=None,
        clear_vacation_days_override=True,
        status=None,
    )

    update_query, *update_args = connection.fetchrow.call_args[0]
    assert update_args[7] is True  # clear_vacation_days_override
    connection.execute.assert_awaited_once()
    balance_args = connection.execute.call_args[0][1:]
    assert balance_args == ("user-1", 20.0)


@pytest.mark.asyncio
async def test_update_staff_member_setting_a_new_override_recomputes_balance():
    connection = _FakeConnection()
    connection.fetchrow.return_value = {
        "id": "user-1",
        "hire_date": date(2020, 1, 1),  # calcularía 20, pero manda el override
        "vacation_days_override": 15,
    }
    pool = _FakePool(connection)
    pool.fetchrow.return_value = _row()
    repository = PostgresStaffRepository(pool)

    await repository.update_staff_member(
        "user-1",
        job_title=None,
        department_id=None,
        entity_id=None,
        role_id=None,
        is_external=None,
        vacation_days_override=15,
        clear_vacation_days_override=False,
        status=None,
    )

    connection.execute.assert_awaited_once()
    balance_args = connection.execute.call_args[0][1:]
    assert balance_args == ("user-1", 15.0)
