from datetime import datetime, timezone

import pytest

from src.features.auth.application.use_cases.refresh_session import RefreshSessionUseCase
from src.features.auth.domain.entities import AuthenticatedUser
from src.shared.errors.base import InvalidTokenError

from .fakes import FakeJWTService, FakeSessionRepository, FakeUserRepository


def _active_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id="user-1",
        email="empleado@ameliahub.com",
        full_name="Empleado",
        avatar_url=None,
        role_code="empleado",
        role_id="role-empleado",
        entity_id=None,
        department_id=None,
        manager_id=None,
        job_title=None,
        status="active",
        is_external=False,
    )


@pytest.mark.asyncio
async def test_refresh_rotates_session_and_returns_new_tokens():
    user_repo = FakeUserRepository(users=[_active_user()])
    session_repo = FakeSessionRepository()
    await session_repo.create_session(
        user_id="user-1", jti="jti-1", expires_at=datetime.now(timezone.utc), user_agent=None, ip_address=None
    )

    use_case = RefreshSessionUseCase(user_repo, session_repo, FakeJWTService())
    result = await use_case.execute("refresh:user-1:jti-1")

    assert result.access_token == "access:user-1"
    assert session_repo.sessions["jti-1"]["revoked"] is True  # jti viejo, revocado
    assert len(session_repo.sessions) == 2  # se creó una sesión nueva (rotación)


@pytest.mark.asyncio
async def test_refresh_with_revoked_jti_is_rejected():
    user_repo = FakeUserRepository(users=[_active_user()])
    session_repo = FakeSessionRepository()
    await session_repo.create_session(
        user_id="user-1", jti="jti-1", expires_at=datetime.now(timezone.utc), user_agent=None, ip_address=None
    )
    await session_repo.revoke_session("jti-1")

    use_case = RefreshSessionUseCase(user_repo, session_repo, FakeJWTService())

    with pytest.raises(InvalidTokenError):
        await use_case.execute("refresh:user-1:jti-1")


@pytest.mark.asyncio
async def test_refresh_with_unknown_jti_is_rejected():
    """Un refresh token con firma válida pero jti que nunca existió (o de otra BD)."""
    use_case = RefreshSessionUseCase(
        FakeUserRepository(users=[_active_user()]), FakeSessionRepository(), FakeJWTService()
    )

    with pytest.raises(InvalidTokenError):
        await use_case.execute("refresh:user-1:never-existed")


@pytest.mark.asyncio
async def test_refresh_without_token_raises():
    from src.shared.errors.base import TokenNotFoundError

    use_case = RefreshSessionUseCase(FakeUserRepository(), FakeSessionRepository(), FakeJWTService())

    with pytest.raises(TokenNotFoundError):
        await use_case.execute(None)
