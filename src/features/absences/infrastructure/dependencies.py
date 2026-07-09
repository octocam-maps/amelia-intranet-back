"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.shared.database import get_database_pool

from ..application.use_cases.create_absence_request import CreateAbsenceRequestUseCase
from ..application.use_cases.create_absence_type import CreateAbsenceTypeUseCase
from ..application.use_cases.get_absence_balance import GetAbsenceBalanceUseCase
from ..application.use_cases.list_absence_requests import ListAbsenceRequestsUseCase
from ..application.use_cases.list_absence_types import ListAbsenceTypesUseCase
from ..application.use_cases.list_all_absence_types import ListAllAbsenceTypesUseCase
from ..application.use_cases.review_absence_request import ReviewAbsenceRequestUseCase
from ..application.use_cases.update_absence_type import UpdateAbsenceTypeUseCase
from .repositories.absence_repository import PostgresAbsenceRepository


def _get_repository() -> PostgresAbsenceRepository:
    return PostgresAbsenceRepository(get_database_pool())


def get_list_absence_types_use_case() -> ListAbsenceTypesUseCase:
    return ListAbsenceTypesUseCase(_get_repository())


def get_list_all_absence_types_use_case() -> ListAllAbsenceTypesUseCase:
    return ListAllAbsenceTypesUseCase(_get_repository())


def get_create_absence_type_use_case() -> CreateAbsenceTypeUseCase:
    return CreateAbsenceTypeUseCase(_get_repository())


def get_update_absence_type_use_case() -> UpdateAbsenceTypeUseCase:
    return UpdateAbsenceTypeUseCase(_get_repository())


def get_absence_balance_use_case() -> GetAbsenceBalanceUseCase:
    return GetAbsenceBalanceUseCase(_get_repository())


def get_create_absence_request_use_case() -> CreateAbsenceRequestUseCase:
    return CreateAbsenceRequestUseCase(_get_repository())


def get_list_absence_requests_use_case() -> ListAbsenceRequestsUseCase:
    return ListAbsenceRequestsUseCase(_get_repository())


def get_review_absence_request_use_case() -> ReviewAbsenceRequestUseCase:
    return ReviewAbsenceRequestUseCase(_get_repository())
