"""
Puerto (Protocol) del feature `team`. Proyecciones de SOLO LECTURA sobre
tablas de otros features (`users`, `user_profiles`, `entities`,
`absence_requests`, `absence_types`) — ver la nota de diseño en
`domain/entities.py`. `domain` no importa nada de `infrastructure` ni de
FastAPI.
"""

from datetime import date
from typing import Optional, Protocol

from .entities import TeamAbsenceEntry, TeamBirthday, TeamMember


class ITeamRepository(Protocol):
    async def list_directory(self) -> list[TeamMember]:
        """Plantilla activa: excluye `status = 'suspended'` y `deleted_at`
        no nulo. Incluye invitados (`status = 'invited'`) — todavía forman
        parte del directorio aunque no hayan completado el onboarding."""
        ...

    async def get_department_id(self, user_id: str) -> Optional[str]:
        """Departamento ACTUAL del usuario, resuelto en el backend (nunca
        se confía en un claim del cliente/JWT para esto). `None` si el
        usuario no tiene departamento asignado o no existe/está borrado."""
        ...

    async def list_team_absences(
        self, *, department_id: str, year: int, month: int
    ) -> list[TeamAbsenceEntry]:
        """Ausencias `status = 'approved'` de compañeros del MISMO
        `department_id`, cuyo rango solapa el mes `year`-`month`. El `kind`
        de cada entrada ya viene mapeado a `AbsenceKind` — el `code` real
        del tipo de ausencia nunca se selecciona/propaga fuera de esta
        consulta (ver `domain/entities.py`)."""
        ...

    async def list_upcoming_birthdays(self, *, today: date, days: int) -> list[TeamBirthday]:
        """Cumpleaños de la plantilla interna (`is_external = FALSE`, no
        suspendida/borrada) cuyo mes-día de nacimiento cae entre `today` y
        `today + (days - 1)` días — comparando SOLO mes-día, ignorando el
        año, e incluyendo el wrap de fin de año (p.ej. 29-dic + 7 días
        cubre hasta el 4 de enero). Ordenado por proximidad: los de hoy
        primero, luego el resto de la ventana."""
        ...
