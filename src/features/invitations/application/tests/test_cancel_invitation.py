import pytest

from src.features.invitations.application.use_cases.cancel_invitation import (
    CancelInvitationUseCase,
)
from src.features.invitations.domain.errors import (
    InvitationNotCancellableError,
    InvitationNotFoundError,
)

from .fakes import FakeInvitationRepository, build_invitation


@pytest.mark.asyncio
async def test_cancels_a_pending_invitation_and_suspends_the_access():
    invitation = build_invitation(status="pending")
    repository = FakeInvitationRepository([invitation])
    use_case = CancelInvitationUseCase(repository)

    cancelled = await use_case.execute(invitation.id)

    assert cancelled.status == "revoked"
    assert repository.user_status_by_email[invitation.email] == "suspended"


@pytest.mark.asyncio
async def test_cannot_cancel_an_already_cancelled_invitation():
    invitation = build_invitation(status="revoked")
    repository = FakeInvitationRepository([invitation])
    repository.user_status_by_email[invitation.email] = "suspended"
    use_case = CancelInvitationUseCase(repository)

    with pytest.raises(InvitationNotCancellableError):
        await use_case.execute(invitation.id)


@pytest.mark.asyncio
async def test_cannot_cancel_once_the_person_already_logged_in():
    """Deuda conocida (ver `domain/ports.py`): `invitations.status` sigue en
    'pending' aunque la persona ya haya iniciado sesión — cancelar en ese
    caso no debe suspender a alguien con acceso real ya activo."""
    invitation = build_invitation(status="pending")
    repository = FakeInvitationRepository([invitation])
    repository.user_status_by_email[invitation.email] = "active"
    use_case = CancelInvitationUseCase(repository)

    with pytest.raises(InvitationNotCancellableError):
        await use_case.execute(invitation.id)

    assert repository.user_status_by_email[invitation.email] == "active"  # sin tocar


@pytest.mark.asyncio
async def test_cancelling_a_missing_invitation_raises_not_found():
    repository = FakeInvitationRepository()
    use_case = CancelInvitationUseCase(repository)

    with pytest.raises(InvitationNotFoundError):
        await use_case.execute("does-not-exist")
