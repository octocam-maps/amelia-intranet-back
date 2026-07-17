"""Caso de uso: reenviar el email de aviso de una invitación
(docs/permisos-roles.md § "Gestión de plantilla" — admin-only, ver router).
Si ya venció, extiende `expires_at` otros `INVITATION_EXPIRES_DAYS` antes
de reenviar."""

from datetime import datetime, timedelta, timezone

from src.shared.email.domain.ports import IEmailSender
from src.shared.logger import get_logger

from ...domain.entities import Invitation
from ...domain.errors import InvitationAlreadyCancelledError, InvitationNotFoundError
from ...domain.ports import IInvitationRepository

logger = get_logger("invitations.resend_invitation")


class ResendInvitationUseCase:
    def __init__(
        self,
        repository: IInvitationRepository,
        email_sender: IEmailSender,
        invitation_expires_days: int,
        frontend_url: str,
    ):
        self._repository = repository
        self._email_sender = email_sender
        self._invitation_expires_days = invitation_expires_days
        self._frontend_url = frontend_url

    async def execute(self, invitation_id: str) -> Invitation:
        invitation = await self._repository.find_by_id(invitation_id)
        if invitation is None:
            raise InvitationNotFoundError("La invitación no existe.")
        if invitation.status == "revoked":
            raise InvitationAlreadyCancelledError(
                "No se puede reenviar una invitación cancelada."
            )

        if invitation.expires_at <= datetime.now(timezone.utc):
            new_expires_at = datetime.now(timezone.utc) + timedelta(
                days=self._invitation_expires_days
            )
            invitation = await self._repository.update_expiry(invitation_id, new_expires_at)

        # Best-effort, mismo criterio que `staff.CreateStaffMemberUseCase`:
        # un fallo al reenviar el aviso no debe impedir que la invitación
        # quede extendida — RRHH puede volver a pulsar "Reenviar".
        try:
            await self._email_sender.send(
                to=invitation.email,
                template="staff_invited",
                context={"full_name": invitation.full_name, "frontend_url": self._frontend_url},
                user_id=None,
            )
        except Exception as e:
            logger.error(
                "Invitation resend email failed",
                invitation_id=invitation_id,
                email=invitation.email,
                error=str(e),
            )

        return invitation
