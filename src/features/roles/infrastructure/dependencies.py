"""Wiring de FastAPI: construye el caso de uso con su adaptador concreto."""

from src.shared.database import get_database_pool

from ..application.use_cases.list_roles import ListRolesUseCase
from .repositories.role_repository import PostgresRoleRepository


def _get_repository() -> PostgresRoleRepository:
    return PostgresRoleRepository(get_database_pool())


def get_list_roles_use_case() -> ListRolesUseCase:
    return ListRolesUseCase(_get_repository())
