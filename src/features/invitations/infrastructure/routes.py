"""Router de `/invitations`: gestión del ciclo de vida de una invitación
(listar pendientes, reenviar, cancelar) — exclusiva del admin
(docs/permisos-roles.md § "Gestión de plantilla"). El alta en sí sigue
siendo `POST /staff` (feature `staff`); este router solo gestiona lo que
pasa DESPUÉS del alta."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.shared.auth.dependencies import require_role
from src.shared.auth.roles import ADMIN_ONLY

from ..application.use_cases.cancel_invitation import CancelInvitationUseCase
from ..application.use_cases.list_invitations import ListInvitationsUseCase
from ..application.use_cases.resend_invitation import ResendInvitationUseCase
from .dependencies import (
    get_cancel_invitation_use_case,
    get_list_invitations_use_case,
    get_resend_invitation_use_case,
)
from .mappers import invitation_to_dto, invitations_to_dto
from .schemas import InvitationDTO, InvitationListDTO


def create_invitations_router() -> APIRouter:
    router = APIRouter(prefix="/invitations", tags=["invitations"])

    @router.get("", response_model=InvitationListDTO)
    async def list_invitations(
        status: Optional[str] = Query(None, description="Filtra por estado (p.ej. 'pending')"),
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: ListInvitationsUseCase = Depends(get_list_invitations_use_case),
    ):
        invitations = await use_case.execute(status=status)
        return invitations_to_dto(invitations)

    @router.post("/{invitation_id}/resend", response_model=InvitationDTO)
    async def resend_invitation(
        invitation_id: str,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: ResendInvitationUseCase = Depends(get_resend_invitation_use_case),
    ):
        invitation = await use_case.execute(invitation_id)
        return invitation_to_dto(invitation)

    @router.post("/{invitation_id}/cancel", response_model=InvitationDTO)
    async def cancel_invitation(
        invitation_id: str,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: CancelInvitationUseCase = Depends(get_cancel_invitation_use_case),
    ):
        invitation = await use_case.execute(invitation_id)
        return invitation_to_dto(invitation)

    return router
