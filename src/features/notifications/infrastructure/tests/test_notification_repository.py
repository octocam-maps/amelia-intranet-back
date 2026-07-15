"""
Tests de adaptador con el pool mockeado (`AsyncMock`) — mismo patrón que
`features/absences/infrastructure/tests/test_absences_repository.py`. No
requieren Postgres real.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.notifications.infrastructure.repositories.notification_repository import (
    PostgresNotificationRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "notif-1",
        "user_id": "user-1",
        "type": "birthday",
        "title": "¡Feliz cumpleaños!",
        "body": None,
        "data": {"url": "/equipo"},
        "read_at": None,
        "created_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_create_inserts_and_returns_the_notification():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row()
    repository = PostgresNotificationRepository(pool)

    notification = await repository.create(
        user_id="user-1", type="birthday", title="¡Feliz cumpleaños!", body=None, data={"url": "/equipo"}
    )

    assert notification.id == "notif-1"
    assert notification.read is False
    query = pool.fetchrow.call_args[0][0]
    assert "INSERT INTO notifications" in query


@pytest.mark.asyncio
async def test_list_for_user_uses_the_cursor_clause_only_when_before_is_given():
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresNotificationRepository(pool)

    await repository.list_for_user("user-1", limit=20, before=None)
    query_without_cursor = pool.fetch.call_args[0][0]
    assert "created_at <" not in query_without_cursor

    await repository.list_for_user("user-1", limit=20, before=datetime(2026, 7, 1, tzinfo=timezone.utc))
    query_with_cursor = pool.fetch.call_args[0][0]
    assert "created_at <" in query_with_cursor


@pytest.mark.asyncio
async def test_mark_read_scopes_the_update_to_the_owner():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row(read_at=datetime.now(timezone.utc))
    repository = PostgresNotificationRepository(pool)

    notification = await repository.mark_read("notif-1", "user-1")

    assert notification is not None
    query, notification_id, user_id = pool.fetchrow.call_args[0]
    assert "user_id = $2" in query
    assert (notification_id, user_id) == ("notif-1", "user-1")


@pytest.mark.asyncio
async def test_mark_read_returns_none_when_the_update_touches_no_row():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresNotificationRepository(pool)

    notification = await repository.mark_read("notif-1", "someone-elses-id")

    assert notification is None


@pytest.mark.asyncio
async def test_list_anniversary_users_excludes_year_zero():
    """Un `hire_date` de HOY (0 años) no es un aniversario todavía — el
    repositorio filtra `years < 1` en Python porque el filtro real depende
    del año en curso, no de una columna estática."""
    pool = AsyncMock()
    pool.fetch.return_value = [
        {"id": "user-hired-today", "years": 0},
        {"id": "user-1", "years": 3},
    ]
    repository = PostgresNotificationRepository(pool)

    users = await repository.list_anniversary_users(month=7, day=10)

    assert users == [("user-1", 3)]


@pytest.mark.asyncio
async def test_list_announcement_recipient_ids_with_audience_all_only_excludes_externo_invitado():
    pool = AsyncMock()
    pool.fetch.return_value = [{"id": "user-1"}, {"id": "user-2"}]
    repository = PostgresNotificationRepository(pool)

    users = await repository.list_announcement_recipient_ids(
        audience="all", entity_id=None, role_id=None
    )

    assert users == ["user-1", "user-2"]
    query, *params = pool.fetch.call_args[0]
    assert "externo_invitado" in query
    assert params == []


@pytest.mark.asyncio
async def test_list_announcement_recipient_ids_with_audience_entity_filters_by_entity_id():
    pool = AsyncMock()
    pool.fetch.return_value = [{"id": "user-hub-1"}]
    repository = PostgresNotificationRepository(pool)

    users = await repository.list_announcement_recipient_ids(
        audience="entity", entity_id="entity-hub", role_id=None
    )

    assert users == ["user-hub-1"]
    query, *params = pool.fetch.call_args[0]
    assert "externo_invitado" in query
    assert "u.entity_id = $1" in query
    assert params == ["entity-hub"]


@pytest.mark.asyncio
async def test_list_announcement_recipient_ids_with_audience_role_filters_by_role_id():
    pool = AsyncMock()
    pool.fetch.return_value = [{"id": "user-manager-1"}]
    repository = PostgresNotificationRepository(pool)

    users = await repository.list_announcement_recipient_ids(
        audience="role", entity_id=None, role_id="role-empleado"
    )

    assert users == ["user-manager-1"]
    query, *params = pool.fetch.call_args[0]
    assert "externo_invitado" in query
    assert "u.role_id = $1" in query
    assert params == ["role-empleado"]


@pytest.mark.asyncio
async def test_list_announcement_recipient_ids_never_returns_externo_invitado_even_targeted():
    """Si `audience='role'` apunta justo a `externo_invitado`, el AND de
    exclusión deja la consulta sin resultados — no es un bug, es la regla
    de docs/permisos-roles.md § Inicio: ❌ para externo."""
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresNotificationRepository(pool)

    users = await repository.list_announcement_recipient_ids(
        audience="role", entity_id=None, role_id="role-externo_invitado"
    )

    assert users == []


@pytest.mark.asyncio
async def test_list_user_ids_with_open_entry_filters_by_work_date_and_open_clock_out():
    pool = AsyncMock()
    pool.fetch.return_value = [{"user_id": "user-1"}]
    repository = PostgresNotificationRepository(pool)

    users = await repository.list_user_ids_with_open_entry(date(2026, 7, 9))

    assert users == ["user-1"]
    query = pool.fetch.call_args[0][0]
    assert "clock_out IS NULL" in query


@pytest.mark.asyncio
async def test_exists_recipient_notification_with_data_queries_by_user_type_and_data_field():
    pool = AsyncMock()
    pool.fetchval.return_value = True
    repository = PostgresNotificationRepository(pool)

    exists = await repository.exists_recipient_notification_with_data(
        user_id="user-1", type="clock_out_missing", data_key="work_date", data_value="2026-07-09"
    )

    assert exists is True
    query, *params = pool.fetchval.call_args[0]
    assert "data->>$3" in query
    assert params == ["user-1", "clock_out_missing", "work_date", "2026-07-09"]


@pytest.mark.asyncio
async def test_exists_event_notification_with_data_does_not_filter_by_recipient():
    pool = AsyncMock()
    pool.fetchval.return_value = False
    repository = PostgresNotificationRepository(pool)

    exists = await repository.exists_event_notification_with_data(
        type="birthday", data_key="user_id", data_value="user-1"
    )

    assert exists is False
    query, *params = pool.fetchval.call_args[0]
    assert "user_id = $1" not in query
    assert params == ["birthday", "user_id", "user-1"]
