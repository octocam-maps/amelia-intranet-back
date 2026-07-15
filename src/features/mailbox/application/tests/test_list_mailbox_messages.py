import uuid
from datetime import datetime, timezone

import pytest

from src.features.mailbox.application.use_cases.list_mailbox_messages import (
    ListMailboxMessagesUseCase,
)
from src.features.mailbox.domain.entities import AnonymousMessage

from .fakes import FakeMailboxRepository


def _message(status: str) -> AnonymousMessage:
    return AnonymousMessage(
        id=str(uuid.uuid4()),
        reference_code=f"A-{status}",
        category="sugerencia",
        subject=None,
        body="cuerpo",
        status=status,
        admin_reply=None,
        replied_at=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_unread_filter_only_returns_new_messages():
    repository = FakeMailboxRepository(
        messages=[_message("new"), _message("read"), _message("resolved")]
    )
    use_case = ListMailboxMessagesUseCase(repository)

    messages = await use_case.execute(status_filter="unread")

    assert [m.status for m in messages] == ["new"]


@pytest.mark.asyncio
async def test_resolved_filter_only_returns_resolved_messages():
    repository = FakeMailboxRepository(
        messages=[_message("new"), _message("read"), _message("resolved")]
    )
    use_case = ListMailboxMessagesUseCase(repository)

    messages = await use_case.execute(status_filter="resolved")

    assert [m.status for m in messages] == ["resolved"]


@pytest.mark.asyncio
async def test_all_filter_returns_every_status():
    repository = FakeMailboxRepository(
        messages=[_message("new"), _message("read"), _message("resolved")]
    )
    use_case = ListMailboxMessagesUseCase(repository)

    messages = await use_case.execute(status_filter="all")

    assert len(messages) == 3
