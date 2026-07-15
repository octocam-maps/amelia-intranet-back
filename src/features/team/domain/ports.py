"""
Puerto (Protocol) del feature `team`. Proyecciones de SOLO LECTURA sobre
tablas de otros features (`users`, `user_profiles`, `entities`,
`absence_requests`, `absence_types`) — ver la nota de diseño en
`domain/entities.py`. `domain` no importa nada de `infrastructure` ni de
FastAPI.
"""

from datetime import date
from typing import Protocol

from .entities import TeamBirthday, TeamMember, VacationCalendarEntry


class ITeamRepository(Protocol):
    async def list_directory(self) -> list[TeamMember]:
        """Plantilla activa: excluye `status = 'suspended'` y `deleted_at`
        no nulo. Incluye invitados (`status = 'invited'`) — todavía forman
        parte del directorio aunque no hayan completado el onboarding."""
        ...

    async def list_approved_vacations(self, year: int, month: int) -> list[VacationCalendarEntry]:
        """Solo vacaciones (`absence_types.code = 'vacaciones'`) con
        `status = 'approved'` cuyo rango solapa el mes `year`-`month`."""
        ...

    async def list_upcoming_birthdays(self, *, today: date, days: int) -> list[TeamBirthday]:
        """Cumpleaños de la plantilla interna (`is_external = FALSE`, no
        suspendida/borrada) cuyo mes-día de nacimiento cae entre `today` y
        `today + (days - 1)` días — comparando SOLO mes-día, ignorando el
        año, e incluyendo el wrap de fin de año (p.ej. 29-dic + 7 días
        cubre hasta el 4 de enero). Ordenado por proximidad: los de hoy
        primero, luego el resto de la ventana."""
        ...
