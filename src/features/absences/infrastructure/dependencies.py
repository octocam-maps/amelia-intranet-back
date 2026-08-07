"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.features.notifications.infrastructure.dependencies import get_notify_use_case
from src.features.time_clock.application.use_cases.get_compensation_balance import (
    GetCompensationBalanceUseCase,
)
from src.features.time_clock.infrastructure.repositories.time_clock_repository import (
    PostgresTimeClockRepository,
)
from src.shared.database import get_database_pool

from ..application.use_cases.create_absence_request import CreateAbsenceRequestUseCase
from ..application.use_cases.create_absence_type import CreateAbsenceTypeUseCase
from ..application.use_cases.get_absence_balance import GetAbsenceBalanceUseCase
from ..application.use_cases.get_absence_calendar import GetAbsenceCalendarUseCase
from ..application.use_cases.list_absence_requests import ListAbsenceRequestsUseCase
from ..application.use_cases.list_absence_types import ListAbsenceTypesUseCase
from ..application.use_cases.list_all_absence_types import ListAllAbsenceTypesUseCase
from ..application.use_cases.review_absence_request import ReviewAbsenceRequestUseCase
from ..application.use_cases.update_absence_type import UpdateAbsenceTypeUseCase
from ..domain.ports import ICompensationBalanceProvider
from .repositories.absence_repository import PostgresAbsenceRepository


def _get_repository() -> PostgresAbsenceRepository:
    return PostgresAbsenceRepository(get_database_pool())


def get_absence_repository() -> PostgresAbsenceRepository:
    """RF-A1: el router necesita `find_user_full_name` directamente (metadato
    de presentación para el nombre de fichero/cabecera del export
    individual), sin pasar por un caso de uso — mismo criterio que
    `notifications.find_email` (consultado desde donde se necesita
    presentar, no desde el dominio de negocio)."""
    return _get_repository()


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


def get_absence_calendar_use_case() -> GetAbsenceCalendarUseCase:
    return GetAbsenceCalendarUseCase(_get_repository())


class _CompensationBalanceAdapter:
    """Adapta `GetCompensationBalanceUseCase` (feature `time_clock`) al puerto
    `ICompensationBalanceProvider` que consume `absences.application` — mismo
    patrón de recomposición entre features que `_DriveFolderProvisionerAdapter`
    en `staff/infrastructure/dependencies.py`."""

    def __init__(self, use_case: GetCompensationBalanceUseCase):
        self._use_case = use_case

    async def available_minutes(self, user_id: str, year: int) -> int:
        balance = await self._use_case.execute(user_id=user_id, year=year)
        return balance.available_minutes


def _get_compensation_balance_provider() -> ICompensationBalanceProvider:
    return _CompensationBalanceAdapter(
        GetCompensationBalanceUseCase(PostgresTimeClockRepository(get_database_pool()))
    )


def get_create_absence_request_use_case() -> CreateAbsenceRequestUseCase:
    return CreateAbsenceRequestUseCase(
        _get_repository(),
        get_notify_use_case(),
        _get_compensation_balance_provider(),
    )


def get_list_absence_requests_use_case() -> ListAbsenceRequestsUseCase:
    return ListAbsenceRequestsUseCase(_get_repository())


def get_review_absence_request_use_case() -> ReviewAbsenceRequestUseCase:
    return ReviewAbsenceRequestUseCase(_get_repository(), get_notify_use_case())
