"""Cableado del disparador `announcement_published` — fan-out a toda la
plantilla activa salvo `externo_invitado` (docs/permisos-roles.md § Inicio:
❌ para externo). `NotifyUseCase.notify_team_excluding_role` en sí ya tiene
su propia suite en `features/notifications`; aquí solo se verifica que
`Create`/`UpdateAnnouncementUseCase` la invocan en el momento correcto."""

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
        self.team_calls: list[dict] = []

    async def notify_team_excluding_role(self, role_code, **kwargs):
        self.team_calls.append({"role_code": role_code, **kwargs})


@pytest.mark.asyncio
async def test_creating_a_published_announcement_notifies_the_team():
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

    assert len(notify.team_calls) == 1
    assert notify.team_calls[0]["role_code"] == "externo_invitado"
    assert notify.team_calls[0]["type"] == "announcement_published"


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

    assert notify.team_calls == []


@pytest.mark.asyncio
async def test_publishing_a_previous_draft_notifies_the_team():
    repository = FakeAnnouncementRepository()
    draft = await CreateAnnouncementUseCase(repository).execute(
        title="Borrador",
        body="cuerpo",
        author_id="admin-1",
        audience="all",
        entity_code=None,
        role_code=None,
        is_pinned=False,
        published=False,
    )
    notify = _RecordingNotify()
    use_case = UpdateAnnouncementUseCase(repository, notify)

    await use_case.execute(draft.id, published=True)

    assert len(notify.team_calls) == 1


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

    assert notify.team_calls == []
