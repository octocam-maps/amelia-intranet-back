"""Wiring de FastAPI: construye el caso de uso con su adaptador concreto."""

from src.shared.database import get_database_pool

from ..application.use_cases.get_my_profile import GetMyProfileUseCase
from .repositories.profile_repository import PostgresProfileRepository


def _get_repository() -> PostgresProfileRepository:
    return PostgresProfileRepository(get_database_pool())


def get_my_profile_use_case() -> GetMyProfileUseCase:
    return GetMyProfileUseCase(_get_repository())
