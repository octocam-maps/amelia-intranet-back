"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.shared.database import get_database_pool

from ..application.use_cases.create_time_clock_entry import CreateTimeClockEntryUseCase
from ..application.use_cases.delete_time_clock_entry import DeleteTimeClockEntryUseCase
from ..application.use_cases.list_time_clock_entries import ListTimeClockEntriesUseCase
from ..application.use_cases.update_time_clock_entry import UpdateTimeClockEntryUseCase
from .repositories.time_clock_repository import PostgresTimeClockRepository


def _get_repository() -> PostgresTimeClockRepository:
    return PostgresTimeClockRepository(get_database_pool())


def get_create_time_clock_entry_use_case() -> CreateTimeClockEntryUseCase:
    return CreateTimeClockEntryUseCase(_get_repository())


def get_list_time_clock_entries_use_case() -> ListTimeClockEntriesUseCase:
    return ListTimeClockEntriesUseCase(_get_repository())


def get_update_time_clock_entry_use_case() -> UpdateTimeClockEntryUseCase:
    return UpdateTimeClockEntryUseCase(_get_repository())


def get_delete_time_clock_entry_use_case() -> DeleteTimeClockEntryUseCase:
    return DeleteTimeClockEntryUseCase(_get_repository())
