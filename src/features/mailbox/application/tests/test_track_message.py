import pytest

from src.features.mailbox.application.use_cases.submit_anonymous_message import (
    SubmitAnonymousMessageUseCase,
)
from src.features.mailbox.application.use_cases.track_message import TrackMailboxMessageUseCase
from src.features.mailbox.domain.errors import MailboxMessageNotFoundError

from .fakes import FakeMailboxRepository


@pytest.mark.asyncio
async def test_sender_can_track_their_own_message_by_reference_code():
    repository = FakeMailboxRepository()
    message = await SubmitAnonymousMessageUseCase(repository).execute(
        category="sugerencia", subject=None, body="cuerpo"
    )
    use_case = TrackMailboxMessageUseCase(repository)

    tracked = await use_case.execute(reference_code=message.reference_code)

    assert tracked.id == message.id


@pytest.mark.asyncio
async def test_unknown_reference_code_raises_not_found():
    repository = FakeMailboxRepository()
    use_case = TrackMailboxMessageUseCase(repository)

    with pytest.raises(MailboxMessageNotFoundError):
        await use_case.execute(reference_code="NOPE")
