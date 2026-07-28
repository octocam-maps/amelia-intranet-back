"""
Caso de uso: "Calendario general de la plantilla" (LOTE 4) — vista de RRHH
del administrador y del rol `socio` [migración 024] (visión global del
calendario de vacaciones, sin el resto de permisos de Administración) — y,
desde RF-A1, también el export individual de un Empleado sobre SUS PROPIAS
ausencias.

A diferencia de `ListAbsenceRequestsUseCase(mode="all")` (histórico completo
de TODAS las solicitudes, sin acotar por fecha, pensado para el gantt de
gestión ya existente en Ausencias), este caso de uso PIDE un rango de fechas
concreto y solo devuelve `pending`/`approved` — la pregunta que responde es
"¿quién está o va a estar ausente entre estas dos fechas?", no un histórico
de revisión. Lo consumen tanto la pantalla del calendario general como los
exports PDF/XLSX (mismo rango, mismos datos).

Scoping RGPD (RF-A1): el chequeo fino de "¿puede este `requester_id` pedir el
calendario de OTRO `user_id`?" vive AQUÍ, no en el router — mismo patrón que
`GetAbsenceBalanceUseCase` (defensa en profundidad: el use case no debe
confiar solo en `require_role`). El router solo hace el gate de rol grueso
(`INTERNAL_ROLES` en los exports, `ADMIN_SOCIO` en `/calendar/all`, sin
cambios de comportamiento en este último).
"""

from datetime import date

from src.shared.auth.roles import ADMIN_SOCIO, RoleCode

from ...domain.entities import AbsenceCalendarEntry
from ...domain.errors import AbsenceForbiddenError
from ...domain.ports import IAbsenceRepository


class GetAbsenceCalendarUseCase:
    def __init__(self, repository: IAbsenceRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        requester_id: str,
        requester_role: str,
        date_from: date,
        date_to: date,
        user_id: str | None = None,
    ) -> list[AbsenceCalendarEntry]:
        if requester_role in ADMIN_SOCIO:
            # Admin/Socio: cualquier `user_id`, o ninguno -> global. Sin
            # restricción (comportamiento actual, no debe romperse).
            effective_user_id = user_id
        elif requester_role == RoleCode.EMPLEADO:
            # Ausente -> se resuelve al propio; presente e igual al propio
            # -> OK; distinto -> 403.
            effective_user_id = user_id or requester_id
            if effective_user_id != requester_id:
                raise AbsenceForbiddenError(
                    "No puedes consultar el calendario de ausencias de otro usuario."
                )
        else:
            # `externo_invitado` (u otro rol inesperado): el router ya lo
            # rechaza en los 3 endpoints, esto es solo defensa en profundidad.
            raise AbsenceForbiddenError(
                "No tienes permiso para consultar el calendario de ausencias."
            )

        return await self._repository.list_calendar_entries(
            date_from=date_from, date_to=date_to, user_id=effective_user_id
        )
