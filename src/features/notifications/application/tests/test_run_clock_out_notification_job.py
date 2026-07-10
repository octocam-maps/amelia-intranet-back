from datetime import date

import pytest

from src.features.notifications.application.use_cases.notify import NotifyUseCase
from src.features.notifications.application.use_cases.run_clock_out_notification_job import (
    RunClockOutNotificationJobUseCase,
)

from .fakes import FakeEmailSender, FakeNotificationRepository


@pytest.mark.asyncio
async def test_clock_out_job_notifies_each_worker_with_an_open_entry():
    repository = FakeNotificationRepository()
    repository.user_ids_with_open_entry = ["user-1", "user-2"]
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunClockOutNotificationJobUseCase(repository, notify)

    result = await use_case.execute(work_date=date(2026, 7, 9))

    assert result == {"work_date": "2026-07-09", "users_notified": 2}
    clock_out_notifications = [
        n for n in repository.notifications.values() if n.type == "clock_out_missing"
    ]
    assert {n.user_id for n in clock_out_notifications} == {"user-1", "user-2"}


@pytest.mark.asyncio
async def test_clock_out_job_defaults_to_yesterday_when_no_date_is_given():
    repository = FakeNotificationRepository()
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunClockOutNotificationJobUseCase(repository, notify)

    result = await use_case.execute()

    from datetime import timedelta

    assert result["work_date"] == (date.today() - timedelta(days=1)).isoformat()
