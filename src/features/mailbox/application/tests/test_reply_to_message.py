import pytest

from src.features.mailbox.application.use_cases.reply_to_message import (
    ReplyToMailboxMessageUseCase,
)
from src.features.mailbox.application.use_cases.submit_anonymous_message import (
    SubmitAnonymousMessageUseCase,
)
from src.features.mailbox.domain.errors import MailboxMessageNotFoundError

from .fakes import FakeMailboxRepository


@pytest.mark.asyncio
async def test_reply_moves_new_message_to_read():
    repository = FakeMailboxRepository()
    message = await SubmitAnonymousMessageUseCase(repository).execute(
        category="consulta", subject=None, body="¿Parking?"
    )
    use_case = ReplyToMailboxMessageUseCase(repository)

    updated = await use_case.execute(message_id=message.id, admin_reply="Sí, hay 3 plazas libres.")

    assert updated.admin_reply == "Sí, hay 3 plazas libres."
    assert updated.status == "read"
    assert updated.replied_at is not None


@pytest.mark.asyncio
async def test_reply_to_missing_message_raises_not_found():
    repository = FakeMailboxRepository()
    use_case = ReplyToMailboxMessageUseCase(repository)

    with pytest.raises(MailboxMessageNotFoundError):
        await use_case.execute(message_id="does-not-exist", admin_reply="hola")
