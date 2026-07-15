import pytest

from src.features.announcements.application.use_cases.create_announcement import (
    CreateAnnouncementUseCase,
)
from src.features.announcements.domain.errors import InvalidAudienceTargetError

from .fakes import FakeAnnouncementRepository


@pytest.mark.asyncio
async def test_creates_and_publishes_an_announcement_for_everyone_by_default():
    repository = FakeAnnouncementRepository()
    use_case = CreateAnnouncementUseCase(repository)

    announcement = await use_case.execute(
        title="Nueva política de vacaciones",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=True,
    )

    assert announcement.published_at is not None
    assert announcement.audience == "all"


@pytest.mark.asyncio
async def test_can_create_an_unpublished_draft():
    repository = FakeAnnouncementRepository()
    use_case = CreateAnnouncementUseCase(repository)

    announcement = await use_case.execute(
        title="Borrador",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=False,
    )

    assert announcement.published_at is None


@pytest.mark.asyncio
async def test_audience_entity_requires_a_valid_entity_code():
    repository = FakeAnnouncementRepository()
    use_case = CreateAnnouncementUseCase(repository)

    with pytest.raises(InvalidAudienceTargetError):
        await use_case.execute(
            title="Solo Lab",
            body="cuerpo",
            author_id="admin-1",
            audience="entity",
            entity_code=None,
            role_code=None,
            is_pinned=False,
            published=True,
        )


@pytest.mark.asyncio
async def test_audience_role_resolves_role_id():
    repository = FakeAnnouncementRepository()
    use_case = CreateAnnouncementUseCase(repository)

    announcement = await use_case.execute(
        title="Solo empleados",
        body="cuerpo",
        author_id="admin-1",
        audience="role",
        entity_code=None,
        role_code="empleado",
        is_pinned=False,
        published=True,
    )

    assert announcement.role_code == "empleado"
