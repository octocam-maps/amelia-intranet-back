"""
Puerto (Protocol) del feature `announcements`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from datetime import datetime
from typing import Optional, Protocol

from .entities import Announcement


class IAnnouncementRepository(Protocol):
    async def list_all(self) -> list[Announcement]:
        """Vista de gestión del admin: TODOS los anuncios no borrados,
        publicados o no, sin filtrar por audiencia (docs/permisos-roles.md
        § "Anuncios" — el admin gestiona el tablón completo)."""
        ...

    async def list_feed(
        self, *, role_code: str, entity_id: Optional[str], limit: Optional[int]
    ) -> list[Announcement]:
        """Feed de lectura: solo publicados, solo los que aplican a este
        usuario (`audience='all'` o coincide con su entidad/rol). Sirve
        tanto a la tarjeta del dashboard (`limit`) como a un futuro listado
        completo."""
        ...

    async def find_by_id(self, announcement_id: str) -> Optional[Announcement]: ...

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]: ...

    async def resolve_role_id(self, role_code: str) -> Optional[str]: ...

    async def create(
        self,
        *,
        title: str,
        body: str,
        author_id: str,
        audience: str,
        entity_id: Optional[str],
        role_id: Optional[str],
        is_pinned: bool,
        published_at: Optional[datetime],
    ) -> Announcement: ...

    async def update(
        self,
        announcement_id: str,
        *,
        title: Optional[str],
        body: Optional[str],
        audience: Optional[str],
        entity_id: Optional[str],
        role_id: Optional[str],
        clear_entity: bool,
        clear_role: bool,
        is_pinned: Optional[bool],
        published: Optional[bool],
    ) -> Optional[Announcement]:
        """Actualización parcial: cada parámetro en `None` significa "no
        tocar esta columna". `clear_entity`/`clear_role` existen porque
        cambiar de audiencia (p.ej. `entity` -> `all`) necesita poder
        VACIAR una columna, algo que `COALESCE` no distingue de "no
        tocar"."""
        ...

    async def soft_delete(self, announcement_id: str) -> bool:
        """`True` si existía y se marcó `deleted_at` — desaparece del feed y
        de la gestión (mismo patrón que `employee_documents.deleted_at`)."""
        ...
