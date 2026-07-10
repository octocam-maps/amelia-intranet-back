"""Cableado del disparador `announcement_published` — fan-out ACOTADO A LA
MISMA AUDIENCIA que el anuncio (`all`/`entity`/`role`), excluyendo siempre
`externo_invitado` (docs/permisos-roles.md § Inicio: ❌ para externo).
`NotifyUseCase.notify_announcement` en sí ya tiene su propia suite en
`features/notifications`; aquí solo se verifica que `Create`/
`UpdateAnnouncementUseCase` la invocan con la audiencia correcta y en el
momento correcto."""

import pytest

from src.features.announcements.application.use_cases.create_announcement import (
    CreateAnnouncementUseCase,
)
from src.features.announcements.application.use_cases.update_announcement import (
    UpdateAnnouncementUseCase,
)

from .fakes import FakeAnnouncementRepository


class _RecordingNotify:
    def __init__(self):
        self.announcement_calls: list[dict] = []

    async def notify_announcement(self, **kwargs):
        self.announcement_calls.append(kwargs)


@pytest.mark.asyncio
async def test_creating_a_published_announcement_notifies_its_audience():
    repository = FakeAnnouncementRepository()
    notify = _RecordingNotify()
    use_case = CreateAnnouncementUseCase(repository, notify)

    await use_case.execute(
        title="Nueva política",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=True,
    )

    assert len(notify.announcement_calls) == 1
    call = notify.announcement_calls[0]
    assert call["audience"] == "all"
    assert call["entity_id"] is None
    assert call["role_id"] is None
    assert call["type"] == "announcement_published"


@pytest.mark.asyncio
async def test_creating_an_entity_scoped_announcement_notifies_with_its_entity_id():
    repository = FakeAnnouncementRepository()
    notify = _RecordingNotify()
    use_case = CreateAnnouncementUseCase(repository, notify)

    await use_case.execute(
        title="Solo Hub",
        body="cuerpo",
        author_id="admin-1",
        audience="entity",
        entity_code="hub",
        role_code=None,
        is_pinned=False,
        published=True,
    )

    assert len(notify.announcement_calls) == 1
    call = notify.announcement_calls[0]
    assert call["audience"] == "entity"
    assert call["entity_id"] == "entity-hub"
    assert call["role_id"] is None


@pytest.mark.asyncio
async def test_creating_a_draft_does_not_notify_anyone():
    repository = FakeAnnouncementRepository()
    notify = _RecordingNotify()
    use_case = CreateAnnouncementUseCase(repository, notify)

    await use_case.execute(
        title="Borrador",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=False,
    )

    assert notify.announcement_calls == []


@pytest.mark.asyncio
async def test_publishing_a_previous_draft_notifies_its_audience():
    repository = FakeAnnouncementRepository()
    draft = await CreateAnnouncementUseCase(repository).execute(
        title="Borrador",
        body="cuerpo",
        author_id="admin-1",
        audience="role",
        entity_code=None,
        role_code="empleado",
        is_pinned=False,
        published=False,
    )
    notify = _RecordingNotify()
    use_case = UpdateAnnouncementUseCase(repository, notify)

    await use_case.execute(draft.id, published=True)

    assert len(notify.announcement_calls) == 1
    call = notify.announcement_calls[0]
    assert call["audience"] == "role"
    assert call["role_id"] == "role-empleado"
    assert call["entity_id"] is None


@pytest.mark.asyncio
async def test_editing_an_already_published_announcement_does_not_renotify():
    repository = FakeAnnouncementRepository()
    published = await CreateAnnouncementUseCase(repository).execute(
        title="Ya publicado",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=True,
    )
    notify = _RecordingNotify()
    use_case = UpdateAnnouncementUseCase(repository, notify)

    await use_case.execute(published.id, title="Título editado")

    assert notify.announcement_calls == []
