from ..domain.entities import Invitation
from .schemas import InvitationDTO, InvitationListDTO


def invitation_to_dto(invitation: Invitation) -> InvitationDTO:
    return InvitationDTO(
        id=invitation.id,
        email=invitation.email,
        full_name=invitation.full_name,
        role_code=invitation.role_code,
        entity_code=invitation.entity_code,
        invited_by_name=invitation.invited_by_name,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


def invitations_to_dto(invitations: list[Invitation]) -> InvitationListDTO:
    return InvitationListDTO(invitations=[invitation_to_dto(i) for i in invitations])
