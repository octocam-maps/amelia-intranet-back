import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.features.announcements.application.use_cases.list_announcements import (
    ListAnnouncementsUseCase,
)
from src.features.announcements.domain.entities import Announcement

from .fakes import FakeAnnouncementRepository


def _announcement(
    *,
    audience: str = "all",
    entity_id=None,
    role_code=None,
    published: bool = True,
    is_pinned: bool = False,
) -> Announcement:
    now = datetime.now(timezone.utc)
    return Announcement(
        id=str(uuid.uuid4()),
        title="Comunicado",
        body="cuerpo",
        author_id="admin-1",
        author_full_name="Beatriz Luna",
        audience=audience,
        entity_id=entity_id,
        entity_code=None,
        role_id=None,
        role_code=role_code,
        is_pinned=is_pinned,
        published_at=now - timedelta(days=1) if published else None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_admin_sees_every_announcement_including_drafts():
    repository = FakeAnnouncementRepository(
        [_announcement(published=True), _announcement(published=False)]
    )
    use_case = ListAnnouncementsUseCase(repository)

    result = await use_case.execute(requester_role="administrador", requester_entity_id=None)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_empleado_only_sees_published_announcements_that_apply_to_them():
    repository = FakeAnnouncementRepository(
        [
            _announcement(audience="all", published=True),
            _announcement(audience="all", published=False),
            _announcement(audience="entity", entity_id="entity-lab", published=True),
        ]
    )
    use_case = ListAnnouncementsUseCase(repository)

    result = await use_case.execute(
        requester_role="empleado", requester_entity_id="entity-hub"
    )

    assert len(result) == 1
    assert result[0].audience == "all"


@pytest.mark.asyncio
async def test_empleado_sees_announcements_targeted_at_their_own_entity():
    repository = FakeAnnouncementRepository(
        [
            _announcement(audience="entity", entity_id="entity-hub", published=True),
            _announcement(audience="entity", entity_id="entity-lab", published=True),
        ]
    )
    use_case = ListAnnouncementsUseCase(repository)

    result = await use_case.execute(
        requester_role="empleado", requester_entity_id="entity-hub"
    )

    assert len(result) == 1
    assert result[0].entity_id == "entity-hub"


@pytest.mark.asyncio
async def test_limit_caps_the_feed_for_the_dashboard_card():
    repository = FakeAnnouncementRepository(
        [_announcement(audience="all", published=True) for _ in range(5)]
    )
    use_case = ListAnnouncementsUseCase(repository)

    result = await use_case.execute(
        requester_role="empleado", requester_entity_id=None, limit=2
    )

    assert len(result) == 2
