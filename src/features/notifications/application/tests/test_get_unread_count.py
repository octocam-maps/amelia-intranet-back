import pytest

from src.features.notifications.application.use_cases.get_unread_count import (
    GetUnreadCountUseCase,
)

from .fakes import FakeNotificationRepository


@pytest.mark.asyncio
async def test_get_unread_count_counts_only_the_requesters_unread():
    repository = FakeNotificationRepository()
    await repository.create(user_id="user-1", type="birthday", title="A", body=None, data={})
    await repository.create(user_id="user-1", type="birthday", title="B", body=None, data={})
    use_case = GetUnreadCountUseCase(repository)

    count = await use_case.execute(user_id="user-1")

    assert count == 2
