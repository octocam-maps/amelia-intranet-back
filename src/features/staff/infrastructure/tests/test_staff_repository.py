"""
Tests del adaptador asyncpg de `staff` con el pool mockeado (mismo patrón
que `features/absences/infrastructure/tests/test_absences_repository.py`).
`create_staff_member`/`update_staff_member` usan `db.acquire()` +
`connection.transaction()` (igual que `auth.user_repository`), así que se
mockean con un pool/conexión falsos que respetan el mismo protocolo async
context manager que `asyncpg`.
"""

from datetime import datetime, timezone
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

    member = await repository.create_staff_member(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title="Project Manager",
        department_id=None,
        entity_id="entity-hub",
        role_id="role-empleado",
        is_external=False,
        hire_date=None,
        vacation_days_per_year=23,
    )

    assert member.id == "user-1"
    insert_query = connection.fetchval.call_args[0][0]
    assert "INSERT INTO users" in insert_query
    assert "'invited'" in insert_query
    # Se sembró el saldo inicial porque se pasó `vacation_days_per_year`.
    connection.execute.assert_awaited_once()
    balance_query, *balance_args = connection.execute.call_args[0]
    assert "absence_balances" in balance_query
    assert balance_args == ["user-1", 23]


@pytest.mark.asyncio
async def test_create_staff_member_skips_balance_when_no_vacation_days_given():
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
        hire_date=None,
        vacation_days_per_year=None,
    )

    connection.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_staff_member_returns_none_when_not_found():
    connection = _FakeConnection()
    connection.fetchval.return_value = None
    pool = _FakePool(connection)
    repository = PostgresStaffRepository(pool)

    result = await repository.update_staff_member(
        "missing-id",
        job_title="Nuevo puesto",
        department_id=None,
        entity_id=None,
        role_id=None,
        is_external=None,
        vacation_days_per_year=None,
        status=None,
    )

    assert result is None
    pool.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_staff_member_deactivating_sets_status_suspended():
    connection = _FakeConnection()
    connection.fetchval.return_value = "user-1"
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
        vacation_days_per_year=None,
        status="suspended",
    )

    assert updated.status == "suspended"
    update_query, *update_args = connection.fetchval.call_args[0]
    assert "COALESCE($7, status)" in update_query
    assert update_args[-1] == "suspended"
