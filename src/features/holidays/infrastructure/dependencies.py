"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.shared.config import get_settings
from src.shared.database import get_database_pool

from ..application.use_cases.create_holiday import CreateHolidayUseCase
from ..application.use_cases.delete_holiday import DeleteHolidayUseCase
from ..application.use_cases.import_official_holidays import (
    ImportOfficialHolidaysUseCase,
)
from ..application.use_cases.list_holidays import ListHolidaysUseCase
from ..application.use_cases.update_holiday import UpdateHolidayUseCase
from .providers.nager_provider import NagerHolidayProvider
from .repositories.holiday_repository import PostgresHolidayRepository


def _get_repository() -> PostgresHolidayRepository:
    return PostgresHolidayRepository(get_database_pool())


def get_list_holidays_use_case() -> ListHolidaysUseCase:
    return ListHolidaysUseCase(_get_repository())


def get_create_holiday_use_case() -> CreateHolidayUseCase:
    return CreateHolidayUseCase(_get_repository())


def get_update_holiday_use_case() -> UpdateHolidayUseCase:
    return UpdateHolidayUseCase(_get_repository())


def get_delete_holiday_use_case() -> DeleteHolidayUseCase:
    return DeleteHolidayUseCase(_get_repository())


def get_import_official_holidays_use_case() -> ImportOfficialHolidaysUseCase:
    provider = NagerHolidayProvider(get_settings().nager_base_url)
    return ImportOfficialHolidaysUseCase(provider, _get_repository())
