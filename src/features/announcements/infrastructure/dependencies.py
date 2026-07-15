"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.features.notifications.infrastructure.dependencies import get_notify_use_case
from src.shared.database import get_database_pool

from ..application.use_cases.create_announcement import CreateAnnouncementUseCase
from ..application.use_cases.delete_announcement import DeleteAnnouncementUseCase
from ..application.use_cases.list_announcements import ListAnnouncementsUseCase
from ..application.use_cases.update_announcement import UpdateAnnouncementUseCase
from .repositories.announcement_repository import PostgresAnnouncementRepository


def _get_repository() -> PostgresAnnouncementRepository:
    return PostgresAnnouncementRepository(get_database_pool())


def get_list_announcements_use_case() -> ListAnnouncementsUseCase:
    return ListAnnouncementsUseCase(_get_repository())


def get_create_announcement_use_case() -> CreateAnnouncementUseCase:
    return CreateAnnouncementUseCase(_get_repository(), get_notify_use_case())


def get_update_announcement_use_case() -> UpdateAnnouncementUseCase:
    return UpdateAnnouncementUseCase(_get_repository(), get_notify_use_case())


def get_delete_announcement_use_case() -> DeleteAnnouncementUseCase:
    return DeleteAnnouncementUseCase(_get_repository())
