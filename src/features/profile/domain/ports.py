"""
Puerto (Protocol) del feature `profile`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from typing import Optional, Protocol

from .entities import UserProfile


class IProfileRepository(Protocol):
    async def find_profile_by_user_id(self, user_id: str) -> Optional[UserProfile]: ...

    async def update_profile_contact(
        self, user_id: str, *, phone: Optional[str], city: Optional[str]
    ) -> Optional[UserProfile]:
        """Actualización parcial de los datos de contacto propios (semántica
        PATCH: cada parámetro en `None` significa "no tocar este campo", no
        "vaciarlo" — mismo criterio que `IStaffRepository.update_staff_member`).
        `None` de retorno si el usuario no existe (borrado/inexistente)."""
        ...
