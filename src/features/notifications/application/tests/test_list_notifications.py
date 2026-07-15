import pytest

from src.features.notifications.application.use_cases.list_notifications import (
    ListNotificationsUseCase,
)

from .fakes import FakeNotificationRepository


@pytest.mark.asyncio
async def test_list_notifications_only_returns_the_requester_own_notifications():
    repository = FakeNotificationRepository()
    await repository.create(user_id="user-1", type="birthday", title="A", body=None, data={})
    await repository.create(user_id="user-2", type="birthday", title="B", body=None, data={})
    use_case = ListNotificationsUseCase(repository)

    page = await use_case.execute(user_id="user-1", limit=20, before=None)

    assert len(page.items) == 1
    assert page.items[0].user_id == "user-1"
    assert page.next_before is None


@pytest.mark.asyncio
async def test_list_notifications_reports_a_cursor_when_there_is_a_next_page():
    repository = FakeNotificationRepository()
    for i in range(3):
        await repository.create(
            user_id="user-1", type="birthday", title=f"N{i}", body=None, data={}
        )
    use_case = ListNotificationsUseCase(repository)

    page = await use_case.execute(user_id="user-1", limit=2, before=None)

    assert len(page.items) == 2
    assert page.next_before is not None
