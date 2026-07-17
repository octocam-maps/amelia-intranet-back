from datetime import datetime, timedelta, timezone

import pytest

from src.features.invitations.application.use_cases.resend_invitation import (
    ResendInvitationUseCase,
)
from src.features.invitations.domain.errors import (
    InvitationAlreadyCancelledError,
    InvitationNotFoundError,
)

from .fakes import FakeEmailSender, FakeInvitationRepository, build_invitation


def _build_use_case(repository, email_sender=None, invitation_expires_days=7):
    return ResendInvitationUseCase(
        repository,
        email_sender or FakeEmailSender(),
        invitation_expires_days,
        "http://localhost:5173",
    )


@pytest.mark.asyncio
async def test_resends_the_email_without_touching_a_still_valid_expiry():
    invitation = build_invitation(expires_at=datetime.now(timezone.utc) + timedelta(days=3))
    repository = FakeInvitationRepository([invitation])
    email_sender = FakeEmailSender()
    use_case = _build_use_case(repository, email_sender)

    result = await use_case.execute(invitation.id)

    assert result.expires_at == invitation.expires_at  # sin tocar: no había vencido
    assert len(email_sender.sent) == 1
    assert email_sender.sent[0]["to"] == invitation.email
    assert email_sender.sent[0]["template"] == "staff_invited"


@pytest.mark.asyncio
async def test_resending_an_expired_invitation_extends_expires_at():
    invitation = build_invitation(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    repository = FakeInvitationRepository([invitation])
    use_case = _build_use_case(repository, invitation_expires_days=7)

    result = await use_case.execute(invitation.id)

    assert result.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_cannot_resend_a_cancelled_invitation():
    invitation = build_invitation(status="revoked")
    repository = FakeInvitationRepository([invitation])
    use_case = _build_use_case(repository)

    with pytest.raises(InvitationAlreadyCancelledError):
        await use_case.execute(invitation.id)


@pytest.mark.asyncio
async def test_resending_a_missing_invitation_raises_not_found():
    repository = FakeInvitationRepository()
    use_case = _build_use_case(repository)

    with pytest.raises(InvitationNotFoundError):
        await use_case.execute("does-not-exist")


@pytest.mark.asyncio
async def test_email_failure_does_not_prevent_the_extension():
    """Best-effort, mismo criterio que `staff.CreateStaffMemberUseCase`."""
    invitation = build_invitation(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    repository = FakeInvitationRepository([invitation])
    email_sender = FakeEmailSender(fail_for={invitation.email})
    use_case = _build_use_case(repository, email_sender)

    result = await use_case.execute(invitation.id)

    assert result.expires_at > datetime.now(timezone.utc)
    assert email_sender.sent == []
