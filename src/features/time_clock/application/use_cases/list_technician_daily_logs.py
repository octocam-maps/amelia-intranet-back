"""
Caso de uso: listar los partes de un técnico en un mes natural, y derivar de
ellos el resumen que encabeza la pantalla y el Excel.

El resumen se calcula A PARTIR DE LOS PARTES YA TRAÍDOS, no con una consulta
agregada aparte: son como mucho 31 filas, y así es imposible que la tabla y
los totales se contradigan por haber consultado en dos momentos distintos.
"""

import calendar
from datetime import date

from src.shared.auth.roles import RoleCode
from src.shared.utils.timezone import today_in_madrid

from ...domain.entities import OvernightStay, TechnicianDailyLog
from ...domain.errors import TimeClockForbiddenError
from ...domain.policy import (
    MONTHLY_HOURS_BUDGET_MINUTES,
    compensation_minutes,
    overtime_minutes,
)
from ...domain.ports import ITimeClockRepository
from ..results import TechnicianMonthSummary


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Del día 1 al último del mes, que es exactamente el periodo de la bolsa
    de 162 h que definió RRHH."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def build_month_summary(
    logs: list[TechnicianDailyLog], *, year: int, month: int, today: date
) -> TechnicianMonthSummary:
    worked = sum(log.worked_minutes for log in logs)
    overtime = overtime_minutes(worked)
    _, month_end = month_bounds(year, month)

    return TechnicianMonthSummary(
        year=year,
        month=month,
        budget_minutes=MONTHLY_HOURS_BUDGET_MINUTES,
        worked_minutes=worked,
        overtime_minutes=overtime,
        compensation_minutes=compensation_minutes(overtime),
        overnight_stays_spain=sum(
            1 for log in logs if log.overnight_stay is OvernightStay.ESPANA
        ),
        overnight_stays_abroad=sum(
            1 for log in logs if log.overnight_stay is OvernightStay.EXTRANJERO
        ),
        is_closed=month_end < today,
    )


class ListTechnicianDailyLogsUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        requester_id: str,
        requester_role: str,
        year: int,
        month: int,
        user_id: str | None = None,
    ) -> tuple[list[TechnicianDailyLog], TechnicianMonthSummary]:
        target_user_id = user_id or requester_id

        # RGPD: el técnico solo ve lo suyo. El filtrado vive aquí, no en la UI
        # — escribir la URL a mano con el id de otro no debe dar acceso.
        if requester_role != RoleCode.ADMINISTRADOR and target_user_id != requester_id:
            raise TimeClockForbiddenError("Solo puedes consultar tus propios partes.")

        date_from, date_to = month_bounds(year, month)
        logs = await self._repository.list_daily_logs(
            target_user_id, date_from=date_from, date_to=date_to
        )
        summary = build_month_summary(
            logs, year=year, month=month, today=today_in_madrid()
        )
        return logs, summary
