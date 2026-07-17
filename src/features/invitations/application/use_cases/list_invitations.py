"""Caso de uso: listar invitaciones (bandeja del admin en "Plantilla" —
docs/permisos-roles.md § "Gestión de plantilla"). Pass-through deliberado
sobre el repositorio, igual criterio que `roles.ListRolesUseCase`: el
filtrado real (incluida la corrección de la deuda conocida sobre
`status='pending'`) vive en el adaptador, no aquí."""

from typing import Optional

from ...domain.entities import Invitation
from ...domain.ports import IInvitationRepository


class ListInvitationsUseCase:
    def __init__(self, repository: IInvitationRepository):
        self._repository = repository

    async def execute(self, *, status: Optional[str] = None) -> list[Invitation]:
        return await self._repository.list_invitations(status=status)
