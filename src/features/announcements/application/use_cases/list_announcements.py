"""Caso de uso: listado de anuncios, condicionado por rol
(docs/permisos-roles.md § "Anuncios"):
- Admin: ve TODOS los anuncios (publicados o no) — es la vista de gestión.
- Cualquier otro rol (empleado/socio/externo_invitado): ve solo el feed que
  le aplica (publicados + audiencia propia) — es la tarjeta del dashboard
  (o del "Inicio" recortado del externo), de ahí el `limit` opcional.

El rol en sí NO se valida aquí — la ruta que llama a este caso de uso ya
decide con `require_role` quién puede llegar hasta aquí; este caso de uso
solo distingue "es admin" de "no lo es" para elegir feed completo vs. feed
filtrado por audiencia.
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
