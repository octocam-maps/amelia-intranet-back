from datetime import date

import pytest

from src.features.notifications.application.use_cases.notify import NotifyUseCase
from src.features.notifications.application.use_cases.run_daily_notification_job import (
    RunDailyNotificationJobUseCase,
)

from .fakes import FakeEmailSender, FakeNotificationRepository


@pytest.mark.asyncio
async def test_daily_job_notifies_the_whole_team_of_a_birthday_except_the_birthday_person():
    """Bug real (auditoría QA): el cumpleañero NO recibe su propia
    notificación en tercera persona ("¡Hoy es el cumpleaños de Ana!" no
    tiene sentido si Ana es quien la lee)."""
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
    assert {n.user_id for n in team_notifications} == {"user-2", "user-3"}


@pytest.mark.asyncio
async def test_daily_job_does_not_duplicate_a_birthday_batch_if_run_twice_the_same_day():
    """Idempotencia (bug real, auditoría QA): reejecutar el job el mismo día
    no debe duplicar el lote de notificaciones a todo el equipo ni reenviar
    el email."""
    repository = FakeNotificationRepository()
    repository.birthday_users = [("user-1", "Ana García")]
    repository.active_user_ids_by_excluded_role = {
        "externo_invitado": ["user-1", "user-2", "user-3"]
    }
    email_sender = FakeEmailSender()
    repository.emails_by_user = {"user-2": "user2@ameliahub.com", "user-3": "user3@ameliahub.com"}
    notify = NotifyUseCase(repository, email_sender)
    use_case = RunDailyNotificationJobUseCase(repository, notify)

    first_run = await use_case.execute(today=date(2026, 7, 10))
    second_run = await use_case.execute(today=date(2026, 7, 10))

    assert first_run["birthdays_notified"] == 1
    assert second_run["birthdays_notified"] == 0
    team_notifications = [n for n in repository.notifications.values() if n.type == "birthday"]
    assert len(team_notifications) == 2  # user-2 + user-3, no duplicados
    assert len(email_sender.sent) == 2


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
async def test_daily_job_does_not_duplicate_an_anniversary_notification_if_run_twice():
    """Idempotencia (bug real, auditoría QA): reejecutar el job el mismo día
    no debe duplicar el aviso de aniversario ni reenviar el email."""
    repository = FakeNotificationRepository()
    repository.anniversary_users = [("user-1", 3)]
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunDailyNotificationJobUseCase(repository, notify)

    first_run = await use_case.execute(today=date(2026, 7, 10))
    second_run = await use_case.execute(today=date(2026, 7, 10))

    assert first_run["anniversaries_notified"] == 1
    assert second_run["anniversaries_notified"] == 0
    anniversary_notifications = [
        n for n in repository.notifications.values() if n.type == "work_anniversary"
    ]
    assert len(anniversary_notifications) == 1


@pytest.mark.asyncio
async def test_daily_job_is_a_no_op_when_nobody_has_a_birthday_or_anniversary():
    repository = FakeNotificationRepository()
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunDailyNotificationJobUseCase(repository, notify)

    result = await use_case.execute(today=date(2026, 7, 10))

    assert result == {"birthdays_notified": 0, "anniversaries_notified": 0}
    assert repository.notifications == {}
