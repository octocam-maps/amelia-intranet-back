from datetime import date

import pytest

from src.features.notifications.application.use_cases.notify import NotifyUseCase
from src.features.notifications.application.use_cases.run_daily_notification_job import (
    RunDailyNotificationJobUseCase,
)

from .fakes import FakeEmailSender, FakeNotificationRepository


@pytest.mark.asyncio
async def test_daily_job_notifies_the_whole_team_of_a_birthday():
    repository = FakeNotificationRepository()
    repository.birthday_users = [("user-1", "Ana García")]
    repository.active_user_ids_by_excluded_role = {
        "externo_invitado": ["user-1", "user-2", "user-3"]
    }
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunDailyNotificationJobUseCase(repository, notify)

    result = await use_case.execute(today=date(2026, 7, 10))

    assert result["birthdays_notified"] == 1
    team_notifications = [n for n in repository.notifications.values() if n.type == "birthday"]
    assert {n.user_id for n in team_notifications} == {"user-1", "user-2", "user-3"}


@pytest.mark.asyncio
async def test_daily_job_notifies_only_the_worker_of_their_own_anniversary():
    repository = FakeNotificationRepository()
    repository.anniversary_users = [("user-1", 3)]
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunDailyNotificationJobUseCase(repository, notify)

    result = await use_case.execute(today=date(2026, 7, 10))

    assert result["anniversaries_notified"] == 1
    anniversary_notifications = [
        n for n in repository.notifications.values() if n.type == "work_anniversary"
    ]
    assert len(anniversary_notifications) == 1
    assert anniversary_notifications[0].user_id == "user-1"
    assert anniversary_notifications[0].data["years"] == 3


@pytest.mark.asyncio
async def test_daily_job_is_a_no_op_when_nobody_has_a_birthday_or_anniversary():
    repository = FakeNotificationRepository()
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunDailyNotificationJobUseCase(repository, notify)

    result = await use_case.execute(today=date(2026, 7, 10))

    assert result == {"birthdays_notified": 0, "anniversaries_notified": 0}
    assert repository.notifications == {}
