"""
Tests del adaptador asyncpg de `invitations` con el pool mockeado (mismo
patrón que
`features/staff/infrastructure/tests/test_staff_repository.py`).
`cancel_invitation` usa `db.acquire()` + `connection.transaction()`, así que
se mockea con un pool/conexión falsos que respetan el mismo protocolo async
context manager que `asyncpg`.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.invitations.infrastructure.repositories.invitation_repository import (
    PostgresInvitationRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "inv-1",
        "email": "sandra@ameliahub.com",
        "full_name": "Sandra Ramírez",
        "role_id": "role-empleado",
        "role_code": "empleado",
        "entity_id": "entity-hub",
        "entity_code": "hub",
        "status": "pending",
        "expires_at": datetime(2026, 7, 24, tzinfo=timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "invited_by_name": "Beatriz Luna",
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
    def __init__(self):
        self.fetchrow = AsyncMock()

    def transaction(self):
        return _NullContext()


class _FakePool:
    def __init__(self, connection: _FakeConnection):
        self.connection = connection
        self.fetch = AsyncMock()
        self.fetchrow = AsyncMock()
        self.execute = AsyncMock()

    def acquire(self):
        return _AcquireContext(self.connection)


@pytest.mark.asyncio
async def test_list_invitations_without_status_does_not_filter():
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresInvitationRepository(pool)

    invitations = await repository.list_invitations(status=None)

    assert len(invitations) == 1
    query = pool.fetch.call_args[0][0]
    assert "WHERE" not in query


@pytest.mark.asyncio
async def test_list_invitations_pending_also_filters_by_user_status_invited():
    """Regresión de la deuda conocida (ver `domain/ports.py`) — sin este
    AND, alguien que ya inició sesión seguiría apareciendo como pendiente."""
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresInvitationRepository(pool)

    await repository.list_invitations(status="pending")

    query, *args = pool.fetch.call_args[0]
    assert "i.status = $1" in query
    assert "u.status = 'invited'" in query
    assert args == ["pending"]


@pytest.mark.asyncio
async def test_list_invitations_revoked_does_not_add_the_pending_workaround():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresInvitationRepository(pool)

    await repository.list_invitations(status="revoked")

    query = pool.fetch.call_args[0][0]
    assert "i.status = $1" in query
    assert "u.status = 'invited'" not in query


@pytest.mark.asyncio
async def test_update_expiry_persists_and_reloads():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row(expires_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    repository = PostgresInvitationRepository(pool)

    invitation = await repository.update_expiry(
        "inv-1", datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    assert invitation.expires_at == datetime(2026, 8, 1, tzinfo=timezone.utc)
    update_query, *update_args = pool.execute.call_args[0]
    assert "UPDATE invitations SET expires_at" in update_query
    assert update_args == ["inv-1", datetime(2026, 8, 1, tzinfo=timezone.utc)]


@pytest.mark.asyncio
async def test_cancel_invitation_revokes_and_suspends_in_one_transaction():
    connection = _FakeConnection()
    connection.fetchrow.side_effect = [
        {"email": "sandra@ameliahub.com"},  # UPDATE invitations ... RETURNING email
        {"id": "user-1"},  # UPDATE users ... RETURNING id
    ]
    pool = _FakePool(connection)
    pool.fetchrow.return_value = _row(status="revoked")
    repository = PostgresInvitationRepository(pool)

    cancelled = await repository.cancel_invitation("inv-1")

    assert cancelled.status == "revoked"
    first_query = connection.fetchrow.call_args_list[0][0][0]
    assert "UPDATE invitations SET status = 'revoked'" in first_query
    second_query, *second_args = connection.fetchrow.call_args_list[1][0]
    assert "UPDATE users SET status = 'suspended'" in second_query
    assert second_args == ["sandra@ameliahub.com"]


@pytest.mark.asyncio
async def test_cancel_invitation_returns_none_when_no_longer_pending():
    connection = _FakeConnection()
    connection.fetchrow.return_value = None  # el UPDATE de invitations no afectó ninguna fila
    pool = _FakePool(connection)
    repository = PostgresInvitationRepository(pool)

    result = await repository.cancel_invitation("inv-1")

    assert result is None
    connection.fetchrow.assert_awaited_once()  # nunca llegó a intentar el UPDATE de users


@pytest.mark.asyncio
async def test_cancel_invitation_returns_none_when_person_already_logged_in():
    connection = _FakeConnection()
    connection.fetchrow.side_effect = [
        {"email": "sandra@ameliahub.com"},
        None,  # el UPDATE de users no afectó ninguna fila: ya no estaba 'invited'
    ]
    pool = _FakePool(connection)
    repository = PostgresInvitationRepository(pool)

    result = await repository.cancel_invitation("inv-1")

    assert result is None
    assert pool.fetchrow.await_count == 0  # no se llegó a recargar con find_by_id
