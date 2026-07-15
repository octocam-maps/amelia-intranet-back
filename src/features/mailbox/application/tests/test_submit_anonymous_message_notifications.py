"""Cableado del disparador `mailbox_message` — destinatarios = admin(s),
SIN ningún dato del remitente (anonimato estructural, ver
`domain/entities.py`). `NotifyUseCase.notify_admins` en sí ya tiene su
propia suite en `features/notifications`; aquí solo se verifica que
`SubmitAnonymousMessageUseCase` la invoca sin filtrar identidad."""

import pytest

from src.features.mailbox.application.use_cases.submit_anonymous_message import (
    SubmitAnonymousMessageUseCase,
)

from .fakes import FakeMailboxRepository


class _RecordingNotify:
    def __init__(self):
        self.admin_calls: list[dict] = []

    async def notify_admins(self, **kwargs):
        self.admin_calls.append(kwargs)


@pytest.mark.asyncio
async def test_submitting_a_message_notifies_the_admin_tray_without_leaking_identity():
    repository = FakeMailboxRepository()
    notify = _RecordingNotify()
    use_case = SubmitAnonymousMessageUseCase(repository, notify)

    await use_case.execute(category="incidencia", subject="Ascensor", body="No funciona el ascensor")

    assert len(notify.admin_calls) == 1
    call = notify.admin_calls[0]
    assert call["type"] == "mailbox_message"
    # Nada del contenido del mensaje (podría identificar al remitente por
    # redacción) llega a la notificación — solo la categoría.
    assert "Ascensor" not in str(call)
    assert "No funciona el ascensor" not in str(call)
    assert "user_id" not in call and "ip" not in str(call).lower()
