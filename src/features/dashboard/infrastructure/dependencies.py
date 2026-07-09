"""Wiring de FastAPI: construye el caso de uso con su adaptador concreto."""

from src.shared.database import get_database_pool

from ..application.use_cases.get_dashboard_summary import GetDashboardSummaryUseCase
from .repositories.dashboard_repository import PostgresDashboardRepository


def get_dashboard_summary_use_case() -> GetDashboardSummaryUseCase:
    return GetDashboardSummaryUseCase(PostgresDashboardRepository(get_database_pool()))
