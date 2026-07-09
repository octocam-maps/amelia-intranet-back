import pytest

from src.features.mailbox.application.use_cases.resolve_message import (
    ResolveMailboxMessageUseCase,
)
from src.features.mailbox.application.use_cases.submit_anonymous_message import (
    SubmitAnonymousMessageUseCase,
)
from src.features.mailbox.domain.errors import MailboxMessageNotFoundError

from .fakes import FakeMailboxRepository


@pytest.mark.asyncio
async def test_resolve_marks_message_as_resolved():
    repository = FakeMailboxRepository()
    message = await SubmitAnonymousMessageUseCase(repository).execute(
        category="incidencia", subject=None, body="El ascensor no va"
    )
    use_case = ResolveMailboxMessageUseCase(repository)

    updated = await use_case.execute(message_id=message.id)

    assert updated.status == "resolved"


@pytest.mark.asyncio
async def test_resolve_missing_message_raises_not_found():
    repository = FakeMailboxRepository()
    use_case = ResolveMailboxMessageUseCase(repository)

    with pytest.raises(MailboxMessageNotFoundError):
        await use_case.execute(message_id="does-not-exist")
