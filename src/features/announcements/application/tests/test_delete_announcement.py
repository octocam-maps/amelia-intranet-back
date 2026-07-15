import pytest

from src.features.announcements.application.use_cases.create_announcement import (
    CreateAnnouncementUseCase,
)
from src.features.announcements.application.use_cases.delete_announcement import (
    DeleteAnnouncementUseCase,
)
from src.features.announcements.domain.errors import AnnouncementNotFoundError

from .fakes import FakeAnnouncementRepository


@pytest.mark.asyncio
async def test_deletes_an_existing_announcement():
    repository = FakeAnnouncementRepository()
    created = await CreateAnnouncementUseCase(repository).execute(
        title="Original",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=True,
    )
    use_case = DeleteAnnouncementUseCase(repository)

    await use_case.execute(created.id)

    assert await repository.find_by_id(created.id) is None


@pytest.mark.asyncio
async def test_raises_not_found_for_an_unknown_announcement():
    repository = FakeAnnouncementRepository()
    use_case = DeleteAnnouncementUseCase(repository)

    with pytest.raises(AnnouncementNotFoundError):
        await use_case.execute("does-not-exist")
