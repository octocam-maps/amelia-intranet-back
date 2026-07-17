"""
Caso de uso: métricas del Home del administrador
(`GET /dashboard/admin/metrics`) — KPIs del periodo. Solo lectura, agrega
`time_clock_entries` y `absence_requests` (ver nota de diseño en
`domain/entities.py`).

Reglas de negocio documentadas aquí (no en el repositorio SQL):

- **Puntualidad**: puntual si la entrada es <= 09:00 hora de Madrid. El KPI
  del periodo se deriva de la serie diaria (`list_daily_trends`) — suma de
  puntuales/total sobre todos los días del rango.
"""

from datetime import timedelta
from typing import Optional

from src.shared.utils.timezone import today_in_madrid

from ...domain.entities import AdminDashboardMetrics, AdminMetricsKPIs, DailyTrendPoint
from ...domain.ports import IDashboardRepository


class GetAdminMetricsUseCase:
    def __init__(self, repository: IDashboardRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        entity_id: Optional[str] = None,
        department_id: Optional[str] = None,
        period_days: int = 14,
    ) -> AdminDashboardMetrics:
        # TZ-1 (ver src/shared/utils/timezone.py): "hoy" es Europe/Madrid.
        today = today_in_madrid()
        from_date = today - timedelta(days=period_days - 1)

        absent_today = await self._repository.count_absent_today(
            today, entity_id, department_id
        )
        pending_approvals = await self._repository.count_pending_absence_approvals(
            entity_id, department_id
        )
        clocked_in_now = await self._repository.count_clocked_in_now_filtered(
            today, entity_id, department_id
        )
        daily_points = await self._repository.list_daily_trends(
            from_date, today, entity_id, department_id
        )

        kpis = AdminMetricsKPIs(
            absent_today=absent_today,
            pending_approvals=pending_approvals,
            clocked_in_now=clocked_in_now,
            punctuality_pct=_period_punctuality_pct(daily_points),
        )

        return AdminDashboardMetrics(kpis=kpis)


def _period_punctuality_pct(points: list[DailyTrendPoint]) -> int:
    total = sum(p.total_entries for p in points)
    punctual = sum(p.punctual_entries for p in points)
    return _pct(punctual, total)


def _pct(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 0
    return round(numerator / denominator * 100)
