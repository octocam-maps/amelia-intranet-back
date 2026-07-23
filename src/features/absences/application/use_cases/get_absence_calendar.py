"""
Caso de uso: "Calendario general de la plantilla" (LOTE 4) — vista de RRHH
del administrador y del rol `socio` [migración 024] (visión global del
calendario de vacaciones, sin el resto de permisos de Administración).

A diferencia de `ListAbsenceRequestsUseCase(mode="all")` (histórico completo
de TODAS las solicitudes, sin acotar por fecha, pensado para el gantt de
gestión ya existente en Ausencias), este caso de uso PIDE un rango de fechas
concreto y solo devuelve `pending`/`approved` — la pregunta que responde es
"¿quién está o va a estar ausente entre estas dos fechas?", no un histórico
de revisión. Lo consumen tanto la pantalla del calendario general como los
exports PDF/XLSX (mismo rango, mismos datos).
"""

from datetime import date

from src.shared.auth.roles import ADMIN_SOCIO

from ...domain.entities import AbsenceCalendarEntry
from ...domain.errors import AbsenceForbiddenError
from ...domain.ports import IAbsenceRepository

# Mismo rol permitido que `require_role(*ADMIN_SOCIO)` en
# `infrastructure/routes.py` — este chequeo es defensa en profundidad
# (el use case no debe confiar solo en el router), así que ambos deben
# mantenerse en sincronía si el permiso cambia.


class GetAbsenceCalendarUseCase:
    def __init__(self, repository: IAbsenceRepository):
        self._repository = repository

    async def execute(
        self, *, requester_role: str, date_from: date, date_to: date
    ) -> list[AbsenceCalendarEntry]:
        if requester_role not in ADMIN_SOCIO:
            raise AbsenceForbiddenError(
                "Solo el administrador o un socio pueden consultar el calendario "
                "general de la plantilla."
            )
        return await self._repository.list_calendar_entries(date_from=date_from, date_to=date_to)
