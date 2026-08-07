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
from src.shared.auth.roles import (
    DAILY_TIME_LOG_ROLES,
    ROLES_WITHOUT_TIME_TRACKING,
    RoleCode,
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
async def test_list_announcement_recipient_ids_with_audience_all_does_not_exclude_socio():
    """Verificación (migración 024, sin cambios de código): el rol `socio`
    es interno y NO debe quedar excluido de las audiencias team/all de
    anuncios/cumpleaños — a diferencia de `externo_invitado`, la exclusión
    es por lista explícita, no por allow-list, así que un rol nuevo queda
    incluido automáticamente salvo que se añada aquí."""
    pool = AsyncMock()
    pool.fetch.return_value = [{"id": "user-1"}]
    repository = PostgresNotificationRepository(pool)

    await repository.list_announcement_recipient_ids(audience="all", entity_id=None, role_id=None)

    query, *_params = pool.fetch.call_args[0]
    assert "socio" not in query


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
async def test_list_user_ids_pending_clock_in_excludes_users_who_already_clocked_in():
    pool = AsyncMock()
    pool.fetch.return_value = [{"id": "user-1"}]
    repository = PostgresNotificationRepository(pool)

    users = await repository.list_user_ids_pending_clock_in(date(2026, 7, 9))

    assert users == ["user-1"]
    query = pool.fetch.call_args[0][0]
    assert "FROM time_clock_entries e" in query
    assert "e.user_id = u.id AND e.work_date = $1" in query


@pytest.mark.asyncio
async def test_list_user_ids_pending_clock_in_excludes_approved_absence():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresNotificationRepository(pool)

    await repository.list_user_ids_pending_clock_in(date(2026, 7, 9))

    query = pool.fetch.call_args[0][0]
    assert "FROM absence_requests a" in query
    assert "a.status = 'approved'" in query
    assert "$1 BETWEEN a.start_date AND a.end_date" in query


@pytest.mark.asyncio
async def test_list_user_ids_pending_clock_in_excludes_holiday_scoped_by_entity():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresNotificationRepository(pool)

    await repository.list_user_ids_pending_clock_in(date(2026, 7, 9))

    query = pool.fetch.call_args[0][0]
    assert "FROM holidays h" in query
    assert "h.entity_id IS NULL OR h.entity_id = u.entity_id" in query


@pytest.mark.asyncio
async def test_list_user_ids_pending_clock_in_excludes_roles_without_time_clock():
    """RF-A4.3: `externo_invitado` y, desde la migración 038, `becario`."""
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresNotificationRepository(pool)

    await repository.list_user_ids_pending_clock_in(date(2026, 7, 9))

    query = pool.fetch.call_args[0][0]
    assert "'externo_invitado'" in query
    assert "'becario'" in query
    assert "r.code NOT IN" in query


@pytest.mark.asyncio
async def test_list_user_ids_pending_clock_in_never_excludes_a_role_that_can_clock_in():
    """El invariante que de verdad importa, y que un `assert` sobre el literal
    del SQL no cubría: la exclusión del recordatorio es EXACTAMENTE el
    complemento de `TIME_CLOCK_ROLES`. Si alguien añade un rol al recordatorio
    sin dárselo al fichaje (o al revés), este test cae — el síntoma en
    producción habría sido un email diario pidiendo fichar a quien recibe un
    403 al intentarlo, o un silencio para quien sí debe fichar."""
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresNotificationRepository(pool)

    await repository.list_user_ids_pending_clock_in(date(2026, 7, 9))

    query = pool.fetch.call_args[0][0]
    excluded_clause = query.split("r.code NOT IN (")[1].split(")")[0]

    for role in DAILY_TIME_LOG_ROLES:
        assert f"'{role.value}'" not in excluded_clause
    for role in ROLES_WITHOUT_TIME_TRACKING:
        assert f"'{role.value}'" in excluded_clause


@pytest.mark.asyncio
async def test_list_user_ids_pending_clock_in_still_reminds_the_technician():
    """Regresión de la migración 051. El técnico NO ficha por tramos, así que
    derivar la exclusión de `TIME_CLOCK_ROLES` —como se hacía antes— le habría
    quitado el recordatorio diario justo a quien el parte le es obligatorio
    cada día. El síntoma habría sido silencioso: nadie echa de menos un email
    que nunca llegó."""
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresNotificationRepository(pool)

    await repository.list_user_ids_pending_clock_in(date(2026, 7, 9))

    query = pool.fetch.call_args[0][0]
    excluded_clause = query.split("r.code NOT IN (")[1].split(")")[0]

    assert f"'{RoleCode.TECNICO.value}'" not in excluded_clause


@pytest.mark.asyncio
async def test_list_user_ids_pending_clock_in_excludes_inactive_users():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresNotificationRepository(pool)

    await repository.list_user_ids_pending_clock_in(date(2026, 7, 9))

    query = pool.fetch.call_args[0][0]
    assert "u.status = 'active'" in query


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
