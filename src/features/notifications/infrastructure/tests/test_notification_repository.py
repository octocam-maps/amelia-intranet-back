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
async def test_list_user_ids_with_open_entry_filters_by_work_date_and_open_clock_out():
    pool = AsyncMock()
    pool.fetch.return_value = [{"user_id": "user-1"}]
    repository = PostgresNotificationRepository(pool)

    users = await repository.list_user_ids_with_open_entry(date(2026, 7, 9))

    assert users == ["user-1"]
    query = pool.fetch.call_args[0][0]
    assert "clock_out IS NULL" in query
