from datetime import date

import pytest

from src.features.notifications.application.use_cases.notify import NotifyUseCase
from src.features.notifications.application.use_cases.run_clock_in_reminder_job import (
    RunClockInReminderJobUseCase,
)

from .fakes import FakeEmailSender, FakeNotificationRepository


@pytest.mark.asyncio
async def test_clock_in_reminder_job_notifies_each_pending_worker():
    repository = FakeNotificationRepository()
    repository.user_ids_pending_clock_in = ["user-1", "user-2"]
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunClockInReminderJobUseCase(repository, notify)

    result = await use_case.execute(work_date=date(2026, 7, 9))  # jueves

    assert result == {"work_date": "2026-07-09", "users_notified": 2}
    reminder_notifications = [
        n for n in repository.notifications.values() if n.type == "clock_in_reminder"
    ]
    assert {n.user_id for n in reminder_notifications} == {"user-1", "user-2"}


@pytest.mark.asyncio
async def test_clock_in_reminder_job_defaults_to_today_not_yesterday():
    """Punto crítico del design (#608): a diferencia de `clock_out` (que
    revisa AYER), este job evalúa el DÍA EN CURSO (RF-A4.6) — nunca
    `date.today() - 1`. Se congela `date.today()` vía el propio resultado
    (comparación directa) para no depender de que el test corra un día
    laborable concreto."""
    repository = FakeNotificationRepository()
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunClockInReminderJobUseCase(repository, notify)

    result = await use_case.execute()

    assert result["work_date"] == date.today().isoformat()


@pytest.mark.asyncio
async def test_clock_in_reminder_job_is_a_no_op_on_saturday_without_touching_the_repo():
    class PoisonedRepository(FakeNotificationRepository):
        async def list_user_ids_pending_clock_in(self, work_date):
            raise AssertionError("no debía consultar BD en fin de semana")

    repository = PoisonedRepository()
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunClockInReminderJobUseCase(repository, notify)

    result = await use_case.execute(work_date=date(2026, 7, 11))  # sábado

    assert result == {"work_date": "2026-07-11", "users_notified": 0}


@pytest.mark.asyncio
async def test_clock_in_reminder_job_is_a_no_op_on_sunday():
    repository = FakeNotificationRepository()
    repository.user_ids_pending_clock_in = ["user-1"]
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunClockInReminderJobUseCase(repository, notify)

    result = await use_case.execute(work_date=date(2026, 7, 12))  # domingo

    assert result == {"work_date": "2026-07-12", "users_notified": 0}


@pytest.mark.asyncio
async def test_clock_in_reminder_job_does_not_duplicate_notifications_when_run_twice():
    """Idempotencia (mismo criterio que `clock_out`): reejecutar el job el
    mismo día para el mismo `work_date` no debe duplicar el aviso ni
    reenviar el email."""
    repository = FakeNotificationRepository()
    repository.user_ids_pending_clock_in = ["user-1", "user-2"]
    notify = NotifyUseCase(repository, FakeEmailSender())
    use_case = RunClockInReminderJobUseCase(repository, notify)

    first_run = await use_case.execute(work_date=date(2026, 7, 9))
    second_run = await use_case.execute(work_date=date(2026, 7, 9))

    assert first_run["users_notified"] == 2
    assert second_run["users_notified"] == 0
    reminder_notifications = [
        n for n in repository.notifications.values() if n.type == "clock_in_reminder"
    ]
    assert len(reminder_notifications) == 2
