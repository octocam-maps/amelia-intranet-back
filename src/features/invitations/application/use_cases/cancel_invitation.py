"""Caso de uso: cancelar una invitación (docs/permisos-roles.md § "Gestión
de plantilla" — admin-only, ver router). Revoca la invitación Y suspende el
acceso (`users.status = 'suspended'`) — reusa la semántica de "baja" que ya
tiene "Plantilla" (`UpdateStaffMemberUseCase`), no hay soft-delete de
usuarios en este proyecto."""

from ...domain.entities import Invitation
from ...domain.errors import InvitationNotCancellableError, InvitationNotFoundError
from ...domain.ports import IInvitationRepository


class CancelInvitationUseCase:
    def __init__(self, repository: IInvitationRepository):
        self._repository = repository

    async def execute(self, invitation_id: str) -> Invitation:
        invitation = await self._repository.find_by_id(invitation_id)
        if invitation is None:
            raise InvitationNotFoundError("La invitación no existe.")

        # RACE-safe (mismo criterio que
        # `absences.update_request_status_if_pending`): el guard real es el
        # UPDATE...WHERE de `cancel_invitation`, no este chequeo optimista.
        cancelled = await self._repository.cancel_invitation(invitation_id)
        if cancelled is None:
            raise InvitationNotCancellableError(
                "Solo se puede cancelar una invitación mientras la persona no haya accedido todavía."
            )
        return cancelled
