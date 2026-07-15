"""
Puerto (Protocol) del feature `profile`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from typing import Optional, Protocol

from .entities import UserProfile


class IProfileRepository(Protocol):
    async def find_profile_by_user_id(self, user_id: str) -> Optional[UserProfile]: ...
