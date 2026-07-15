"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.shared.database import get_database_pool
from src.shared.email import get_email_sender

from ..application.use_cases.get_unread_count import GetUnreadCountUseCase
from ..application.use_cases.list_notifications import ListNotificationsUseCase
from ..application.use_cases.mark_all_notifications_read import MarkAllNotificationsReadUseCase
from ..application.use_cases.mark_notification_read import MarkNotificationReadUseCase
from ..application.use_cases.notify import NotifyUseCase
from ..application.use_cases.run_clock_out_notification_job import (
    RunClockOutNotificationJobUseCase,
)
from ..application.use_cases.run_daily_notification_job import RunDailyNotificationJobUseCase
from .repositories.notification_repository import PostgresNotificationRepository


def _get_repository() -> PostgresNotificationRepository:
    return PostgresNotificationRepository(get_database_pool())


def get_notify_use_case() -> NotifyUseCase:
    """Punto único de wiring del disparador reutilizable — los demás
    features (`absences`, `announcements`, `mailbox`) lo importan para
    cablear sus propios eventos sin conocer el repositorio concreto."""
    return NotifyUseCase(_get_repository(), get_email_sender())


def get_list_notifications_use_case() -> ListNotificationsUseCase:
    return ListNotificationsUseCase(_get_repository())


def get_unread_count_use_case() -> GetUnreadCountUseCase:
    return GetUnreadCountUseCase(_get_repository())


def get_mark_notification_read_use_case() -> MarkNotificationReadUseCase:
    return MarkNotificationReadUseCase(_get_repository())


def get_mark_all_notifications_read_use_case() -> MarkAllNotificationsReadUseCase:
    return MarkAllNotificationsReadUseCase(_get_repository())


def get_run_daily_notification_job_use_case() -> RunDailyNotificationJobUseCase:
    repository = _get_repository()
    return RunDailyNotificationJobUseCase(repository, NotifyUseCase(repository, get_email_sender()))


def get_run_clock_out_notification_job_use_case() -> RunClockOutNotificationJobUseCase:
    repository = _get_repository()
    return RunClockOutNotificationJobUseCase(
        repository, NotifyUseCase(repository, get_email_sender())
    )
