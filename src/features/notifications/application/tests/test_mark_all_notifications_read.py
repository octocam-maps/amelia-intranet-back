import pytest

from src.features.notifications.application.use_cases.mark_all_notifications_read import (
    MarkAllNotificationsReadUseCase,
)

from .fakes import FakeNotificationRepository


@pytest.mark.asyncio
async def test_mark_all_notifications_read_only_touches_the_requesters_unread():
    repository = FakeNotificationRepository()
    await repository.create(user_id="user-1", type="birthday", title="A", body=None, data={})
    await repository.create(user_id="user-1", type="birthday", title="B", body=None, data={})
    await repository.create(user_id="user-2", type="birthday", title="C", body=None, data={})
    use_case = MarkAllNotificationsReadUseCase(repository)

    updated = await use_case.execute(user_id="user-1")

    assert updated == 2
    assert await repository.count_unread("user-1") == 0
    assert await repository.count_unread("user-2") == 1
