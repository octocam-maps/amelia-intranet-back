"""Wiring de FastAPI: construye el caso de uso con su adaptador concreto."""

from src.shared.database import get_database_pool

from ..application.use_cases.list_departments import ListDepartmentsUseCase
from .repositories.department_repository import PostgresDepartmentRepository


def _get_repository() -> PostgresDepartmentRepository:
    return PostgresDepartmentRepository(get_database_pool())


def get_list_departments_use_case() -> ListDepartmentsUseCase:
    return ListDepartmentsUseCase(_get_repository())
