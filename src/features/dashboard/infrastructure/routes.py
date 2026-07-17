"""Router de `/dashboard`: resumen de Inicio, condicionado por rol, y
métricas del Home del administrador."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.shared.auth.dependencies import require_role

from ..application.use_cases.get_admin_metrics import GetAdminMetricsUseCase
from ..application.use_cases.get_dashboard_summary import GetDashboardSummaryUseCase
from .dependencies import get_admin_metrics_use_case, get_dashboard_summary_use_case
from .mappers import metrics_to_dto, summary_to_dto
from .schemas import AdminMetricsDTO, DashboardSummaryDTO


def create_dashboard_router() -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/summary", response_model=DashboardSummaryDTO)
    async def get_summary(
        # El externo-invitado no tiene "Inicio" en la matriz de permisos
        # (docs/permisos-roles.md § Inicio: ❌) — se rechaza aquí, en el
        # backend, no solo ocultando el ítem del navbar. `socio` [migración
        # 024] = igual que empleado -> mismos widgets, nunca la bandeja/vista
        # global del admin (`GetDashboardSummaryUseCase` solo la añade si
        # `role == "administrador"`).
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
        use_case: GetDashboardSummaryUseCase = Depends(get_dashboard_summary_use_case),
    ):
        """Empleado (y socio): sus widgets. Admin: + bandeja de pendientes y vista global."""
        summary = await use_case.execute(user_id=current_user["sub"], role=current_user["role"])
        return summary_to_dto(summary)

    @router.get("/admin/metrics", response_model=AdminMetricsDTO)
    async def get_admin_metrics(
        entity_id: Optional[str] = Query(None),
        department_id: Optional[str] = Query(None),
        period_days: int = Query(14, ge=1, le=90),
        # Exclusivo del admin — igual que el resto de "Administración" en la
        # matriz de permisos, se rechaza en el backend, no solo ocultando el
        # widget en el navbar.
        current_user: dict = Depends(require_role("administrador")),
        use_case: GetAdminMetricsUseCase = Depends(get_admin_metrics_use_case),
    ):
        """KPIs + sparklines del periodo + radar de asistencia (top 5) del
        Home del administrador, acotados opcionalmente por entidad/depto."""
        metrics = await use_case.execute(
            entity_id=entity_id, department_id=department_id, period_days=period_days
        )
        return metrics_to_dto(metrics)

    return router
