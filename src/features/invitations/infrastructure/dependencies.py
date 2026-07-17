"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.shared.config import get_settings
from src.shared.database import get_database_pool
from src.shared.email import get_email_sender

from ..application.use_cases.cancel_invitation import CancelInvitationUseCase
from ..application.use_cases.list_invitations import ListInvitationsUseCase
from ..application.use_cases.resend_invitation import ResendInvitationUseCase
from .repositories.invitation_repository import PostgresInvitationRepository


def _get_repository() -> PostgresInvitationRepository:
    return PostgresInvitationRepository(get_database_pool())


def get_list_invitations_use_case() -> ListInvitationsUseCase:
    return ListInvitationsUseCase(_get_repository())


def get_resend_invitation_use_case() -> ResendInvitationUseCase:
    settings = get_settings()
    return ResendInvitationUseCase(
        _get_repository(),
        get_email_sender(),
        settings.invitation_expires_days,
        settings.frontend_url,
    )


def get_cancel_invitation_use_case() -> CancelInvitationUseCase:
    return CancelInvitationUseCase(_get_repository())
