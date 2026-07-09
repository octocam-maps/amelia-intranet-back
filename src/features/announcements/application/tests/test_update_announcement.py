import pytest

from src.features.announcements.application.use_cases.create_announcement import (
    CreateAnnouncementUseCase,
)
from src.features.announcements.application.use_cases.update_announcement import (
    UpdateAnnouncementUseCase,
)
from src.features.announcements.domain.errors import AnnouncementNotFoundError

from .fakes import FakeAnnouncementRepository


@pytest.mark.asyncio
async def test_updates_only_the_fields_that_are_informed():
    repository = FakeAnnouncementRepository()
    created = await CreateAnnouncementUseCase(repository).execute(
        title="Original",
        body="cuerpo original",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=True,
    )
    use_case = UpdateAnnouncementUseCase(repository)

    updated = await use_case.execute(created.id, is_pinned=True)

    assert updated.is_pinned is True
    assert updated.title == "Original"


@pytest.mark.asyncio
async def test_changing_audience_to_all_clears_the_previous_target():
    repository = FakeAnnouncementRepository()
    created = await CreateAnnouncementUseCase(repository).execute(
        title="Solo Lab",
        body="cuerpo",
        author_id="admin-1",
        audience="entity",
        entity_code="lab",
        role_code=None,
        is_pinned=False,
        published=True,
    )
    use_case = UpdateAnnouncementUseCase(repository)

    updated = await use_case.execute(created.id, audience="all")

    assert updated.audience == "all"
    assert updated.entity_id is None


@pytest.mark.asyncio
async def test_unpublishing_clears_published_at():
    repository = FakeAnnouncementRepository()
    created = await CreateAnnouncementUseCase(repository).execute(
        title="Publicado",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=True,
    )
    use_case = UpdateAnnouncementUseCase(repository)

    updated = await use_case.execute(created.id, published=False)

    assert updated.published_at is None


@pytest.mark.asyncio
async def test_raises_not_found_for_an_unknown_announcement():
    repository = FakeAnnouncementRepository()
    use_case = UpdateAnnouncementUseCase(repository)

    with pytest.raises(AnnouncementNotFoundError):
        await use_case.execute("does-not-exist", title="x")
