"""Wiring de FastAPI: construye los casos de uso con su adaptador concreto."""

from src.shared.database import get_database_pool

from ..application.use_cases.get_vacation_calendar import GetVacationCalendarUseCase
from ..application.use_cases.list_team_directory import ListTeamDirectoryUseCase
from .repositories.team_repository import PostgresTeamRepository


def _get_repository() -> PostgresTeamRepository:
    return PostgresTeamRepository(get_database_pool())


def get_list_team_directory_use_case() -> ListTeamDirectoryUseCase:
    return ListTeamDirectoryUseCase(_get_repository())


def get_vacation_calendar_use_case() -> GetVacationCalendarUseCase:
    return GetVacationCalendarUseCase(_get_repository())
