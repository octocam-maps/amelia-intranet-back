"""Wiring de FastAPI: construye los casos de uso con su adaptador concreto."""

from src.shared.database import get_database_pool

from ..application.use_cases.get_team_calendar import GetTeamCalendarUseCase
from ..application.use_cases.get_upcoming_birthdays import GetUpcomingBirthdaysUseCase
from ..application.use_cases.list_team_directory import ListTeamDirectoryUseCase
from .repositories.team_repository import PostgresTeamRepository


def _get_repository() -> PostgresTeamRepository:
    return PostgresTeamRepository(get_database_pool())


def get_list_team_directory_use_case() -> ListTeamDirectoryUseCase:
    return ListTeamDirectoryUseCase(_get_repository())


def get_team_calendar_use_case() -> GetTeamCalendarUseCase:
    return GetTeamCalendarUseCase(_get_repository())


def get_upcoming_birthdays_use_case() -> GetUpcomingBirthdaysUseCase:
    return GetUpcomingBirthdaysUseCase(_get_repository())
