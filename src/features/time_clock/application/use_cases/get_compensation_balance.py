"""
Caso de uso: saldo ANUAL de descanso por horas extra del técnico.

    devengado  = Σ  max(0, minutos_del_mes − 9720) × 1,45   [meses YA TERMINADOS]
    disfrutado = Σ  ausencias aprobadas de `descanso_horas_extra` × 480 min
    disponible = devengado − disfrutado

Sin tabla de saldos y sin cierre de mes (decisión del team-lead del
2026-08-06): el saldo se recalcula en cada consulta a partir de los partes.

POR QUÉ EL MES EN CURSO NO DEVENGA: la bolsa es mensual y su excedente no se
conoce hasta que el mes termina. Sumarlo al saldo permitiría a alguien pedir
—y disfrutar— el día 10 unas horas extra que el día 28 dejarían de existir
porque se corrigió un parte. Se devuelve aparte, como `pending_minutes`, para
que la UI pueda enseñarlo sin contarlo como disponible.

EL TIPO DE AUSENCIA YA EXISTÍA: `descanso_horas_extra` («Descanso por horas
extra») entró con el catálogo v1.1 de RRHH, migración 032, con
`affects_balance = FALSE`. No se creó uno nuevo — habría duplicado el
concepto y partido en dos el histórico de descansos.
"""

from datetime import date

from src.shared.utils.timezone import today_in_madrid

from ...domain.policy import compensation_minutes, overtime_minutes
from ...domain.ports import ITimeClockRepository
from ..results import CompensationBalance


class GetCompensationBalanceUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, user_id: str, year: int) -> CompensationBalance:
        today = today_in_madrid()
        minutes_by_month = await self._repository.sum_worked_minutes_by_month(
            user_id, year
        )

        accrued = 0
        pending = 0
        for month, worked in minutes_by_month.items():
            devengo = compensation_minutes(overtime_minutes(worked))
            if _month_is_over(year, month, today):
                accrued += devengo
            else:
                pending += devengo

        consumed = await self._repository.sum_compensation_absence_minutes(
            user_id, year
        )

        return CompensationBalance(
            year=year,
            accrued_minutes=accrued,
            consumed_minutes=consumed,
            pending_minutes=pending,
        )


def _month_is_over(year: int, month: int, today: date) -> bool:
    """Un mes de un año pasado siempre está cerrado; del año en curso, solo si
    ya lo hemos dejado atrás. Comparar solo por número de mes daría por cerrado
    enero del año que viene."""
    return (year, month) < (today.year, today.month)
