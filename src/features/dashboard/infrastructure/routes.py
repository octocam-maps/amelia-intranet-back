"""Router de `/dashboard`: resumen de Inicio, condicionado por rol."""

from fastapi import APIRouter, Depends

from src.shared.auth.dependencies import require_role

from ..application.use_cases.get_dashboard_summary import GetDashboardSummaryUseCase
from .dependencies import get_dashboard_summary_use_case
from .mappers import summary_to_dto
from .schemas import DashboardSummaryDTO


def create_dashboard_router() -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/summary", response_model=DashboardSummaryDTO)
    async def get_summary(
        # El externo-invitado no tiene "Inicio" en la matriz de permisos
        # (docs/permisos-roles.md § Inicio: ❌) — se rechaza aquí, en el
        # backend, no solo ocultando el ítem del navbar.
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: GetDashboardSummaryUseCase = Depends(get_dashboard_summary_use_case),
    ):
        """Empleado: sus widgets. Admin: + bandeja de pendientes y vista global."""
        summary = await use_case.execute(user_id=current_user["sub"], role=current_user["role"])
        return summary_to_dto(summary)

    return router
