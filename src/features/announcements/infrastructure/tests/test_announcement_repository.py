"""
Tests del adaptador asyncpg de `announcements` con el pool mockeado (mismo
patrón que `features/mailbox/infrastructure/tests/test_mailbox_repository.py`).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.announcements.infrastructure.repositories.announcement_repository import (
    PostgresAnnouncementRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "ann-1",
        "title": "Comunicado",
        "body": "cuerpo",
        "author_id": "admin-1",
        "author_full_name": "Beatriz Luna",
        "audience": "all",
        "entity_id": None,
        "entity_code": None,
        "role_id": None,
        "role_code": None,
        "is_pinned": False,
        "published_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_feed_filters_by_role_and_entity_and_respects_limit():
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresAnnouncementRepository(pool)

    await repository.list_feed(role_code="empleado", entity_id="entity-hub", limit=3)

    query, *args = pool.fetch.call_args[0]
    assert "published_at IS NOT NULL" in query
    assert "LIMIT $3" in query
    assert args == ["entity-hub", "empleado", 3]


@pytest.mark.asyncio
async def test_list_feed_without_limit_does_not_append_limit_clause():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresAnnouncementRepository(pool)

    await repository.list_feed(role_code="empleado", entity_id=None, limit=None)

    query = pool.fetch.call_args[0][0]
    assert "LIMIT" not in query


@pytest.mark.asyncio
async def test_create_inserts_and_returns_the_full_row():
    pool = AsyncMock()
    pool.fetchrow.side_effect = [{"id": "ann-1"}, _row()]
    repository = PostgresAnnouncementRepository(pool)

    announcement = await repository.create(
        title="Comunicado",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_id=None,
        role_id=None,
        is_pinned=False,
        published_at=datetime.now(timezone.utc),
    )

    assert announcement.id == "ann-1"
    assert announcement.author_full_name == "Beatriz Luna"


@pytest.mark.asyncio
async def test_soft_delete_returns_false_when_announcement_does_not_exist():
    pool = AsyncMock()
    pool.fetchval.return_value = None
    repository = PostgresAnnouncementRepository(pool)

    deleted = await repository.soft_delete("missing-id")

    assert deleted is False


@pytest.mark.asyncio
async def test_soft_delete_returns_true_when_the_row_was_marked():
    pool = AsyncMock()
    pool.fetchval.return_value = "ann-1"
    repository = PostgresAnnouncementRepository(pool)

    deleted = await repository.soft_delete("ann-1")

    assert deleted is True
