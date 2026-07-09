"""
Puerto (Protocol) del feature `team`. Proyecciones de SOLO LECTURA sobre
tablas de otros features (`users`, `user_profiles`, `entities`,
`absence_requests`, `absence_types`) — ver la nota de diseño en
`domain/entities.py`. `domain` no importa nada de `infrastructure` ni de
FastAPI.
"""

from typing import Protocol

from .entities import TeamMember, VacationCalendarEntry


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
