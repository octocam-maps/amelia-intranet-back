"""Caso de uso: listado de anuncios, condicionado por rol
(docs/permisos-roles.md § "Anuncios"):
- Admin: ve TODOS los anuncios (publicados o no) — es la vista de gestión.
- Empleado: ve solo el feed que le aplica (publicados + audiencia propia) —
  es la tarjeta del dashboard, de ahí el `limit` opcional.

El externo-invitado no tiene "Inicio" ni "Anuncios" en la matriz de permisos
(❌) — la ruta que llama a este caso de uso ya lo bloquea con `require_role`
antes de llegar aquí.
"""

from typing import Optional

from ...domain.entities import Announcement
from ...domain.ports import IAnnouncementRepository


class ListAnnouncementsUseCase:
    def __init__(self, repository: IAnnouncementRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        requester_role: str,
        requester_entity_id: Optional[str],
        limit: Optional[int] = None,
    ) -> list[Announcement]:
        if requester_role == "administrador":
            return await self._repository.list_all()

        return await self._repository.list_feed(
            role_code=requester_role, entity_id=requester_entity_id, limit=limit
        )
