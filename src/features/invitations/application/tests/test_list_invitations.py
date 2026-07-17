import pytest

from src.features.invitations.application.use_cases.list_invitations import (
    ListInvitationsUseCase,
)

from .fakes import FakeInvitationRepository, build_invitation


@pytest.mark.asyncio
async def test_lists_all_invitations_without_a_status_filter():
    repository = FakeInvitationRepository(
        [build_invitation(status="pending"), build_invitation(status="revoked")]
    )
    use_case = ListInvitationsUseCase(repository)

    invitations = await use_case.execute()

    assert len(invitations) == 2


@pytest.mark.asyncio
async def test_pending_excludes_invitations_whose_person_already_logged_in():
    """Deuda conocida (ver `domain/ports.py`): `invitations.status` se queda
    en 'pending' para siempre en el alta EAGER actual — sin el cruce contra
    `users.status`, esta lista mostraría como "pendiente" a alguien que ya
    inició sesión."""
    already_active = build_invitation(id="inv-1", email="activa@ameliahub.com", status="pending")
    still_pending = build_invitation(id="inv-2", email="pendiente@ameliahub.com", status="pending")
    repository = FakeInvitationRepository([already_active, still_pending])
    repository.user_status_by_email["activa@ameliahub.com"] = "active"
    use_case = ListInvitationsUseCase(repository)

    invitations = await use_case.execute(status="pending")

    assert [i.id for i in invitations] == ["inv-2"]


@pytest.mark.asyncio
async def test_revoked_filter_does_not_apply_the_pending_workaround():
    revoked = build_invitation(status="revoked")
    repository = FakeInvitationRepository([revoked])
    repository.user_status_by_email[revoked.email] = "suspended"
    use_case = ListInvitationsUseCase(repository)

    invitations = await use_case.execute(status="revoked")

    assert len(invitations) == 1
