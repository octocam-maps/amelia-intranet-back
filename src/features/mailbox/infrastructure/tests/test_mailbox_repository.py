"""
Tests del adaptador asyncpg de `mailbox` con el pool mockeado (mismo patrón
que `features/absences/infrastructure/tests/test_absences_repository.py`).
Foco: el anonimato estructural (el INSERT nunca lleva user_id/IP) y el
reintento ante colisión de `reference_code`.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.mailbox.infrastructure.repositories.mailbox_repository import (
    PostgresMailboxRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "msg-1",
        "reference_code": "AAAAAAAAAAAA",
        "category": "sugerencia",
        "subject": None,
        "body": "cuerpo",
        "status": "new",
        "admin_reply": None,
        "replied_at": None,
        "created_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_create_message_insert_never_takes_a_user_id_or_ip_argument():
    """La firma del puerto (y por tanto del INSERT) no tiene ningún
    parámetro de identidad — el anonimato es estructural, no una
    convención de código que dependa de "no pasar" un argumento."""
    pool = AsyncMock()
    pool.fetchrow.return_value = _row()
    repository = PostgresMailboxRepository(pool)

    await repository.create_message(category="sugerencia", subject="Parking", body="¿Hay plazas?")

    query, *args = pool.fetchrow.call_args[0]
    assert "user_id" not in query
    assert "ip" not in query.lower()
    # reference_code, category, subject, body — nada más.
    assert len(args) == 4


@pytest.mark.asyncio
async def test_create_message_retries_on_reference_code_collision():
    pool = AsyncMock()
    # Primer intento: colisión (ON CONFLICT DO NOTHING -> ninguna fila).
    # Segundo intento: inserción exitosa.
    pool.fetchrow.side_effect = [None, _row()]
    repository = PostgresMailboxRepository(pool)

    message = await repository.create_message(category="consulta", subject=None, body="cuerpo")

    assert pool.fetchrow.call_count == 2
    assert message.reference_code == "AAAAAAAAAAAA"


@pytest.mark.asyncio
async def test_list_messages_unread_filters_by_new_status():
    pool = AsyncMock()
    pool.fetch.return_value = [_row(status="new")]
    repository = PostgresMailboxRepository(pool)

    messages = await repository.list_messages(status_filter="unread")

    assert messages[0].status == "new"
    query, *args = pool.fetch.call_args[0]
    assert "WHERE status = $1" in query
    assert args == ["new"]


@pytest.mark.asyncio
async def test_list_messages_all_has_no_status_filter():
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresMailboxRepository(pool)

    await repository.list_messages(status_filter="all")

    query = pool.fetch.call_args[0][0]
    assert "WHERE" not in query


@pytest.mark.asyncio
async def test_save_reply_returns_none_when_message_does_not_exist():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresMailboxRepository(pool)

    result = await repository.save_reply("missing-id", admin_reply="hola")

    assert result is None


@pytest.mark.asyncio
async def test_mark_resolved_maps_returned_row():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row(status="resolved")
    repository = PostgresMailboxRepository(pool)

    updated = await repository.mark_resolved("msg-1")

    assert updated.status == "resolved"
