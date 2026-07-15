from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.features.auth.application.use_cases.logout import LogoutUseCase

from .fakes import FakeJWTService, FakeSessionRepository


@pytest.mark.asyncio
async def test_logout_revokes_current_session():
    session_repo = FakeSessionRepository()
    await session_repo.create_session(
        user_id="user-1",
        jti="jti-1",
        family_id="fam-1",
        expires_at=datetime.now(timezone.utc),
        user_agent=None,
        ip_address=None,
    )
    use_case = LogoutUseCase(session_repo, FakeJWTService())

    await use_case.execute("refresh:user-1:jti-1")

    assert session_repo.sessions["jti-1"]["revoked"] is True


@pytest.mark.asyncio
async def test_logout_revokes_the_whole_family_not_just_the_jti_presented():
    """Logout revoca la FAMILIA completa — no solo el jti que llegó en la cookie."""
    session_repo = FakeSessionRepository()
    now = datetime.now(timezone.utc)
    await session_repo.create_session(
        user_id="user-1", jti="jti-1", family_id="fam-1", expires_at=now, user_agent=None, ip_address=None
    )
    await session_repo.create_session(
        user_id="user-1", jti="jti-2", family_id="fam-1", expires_at=now, user_agent=None, ip_address=None
    )
    use_case = LogoutUseCase(session_repo, FakeJWTService())

    await use_case.execute("refresh:user-1:jti-2")

    assert session_repo.sessions["jti-1"]["revoked"] is True
    assert session_repo.sessions["jti-2"]["revoked"] is True


@pytest.mark.asyncio
async def test_logout_without_token_does_not_raise():
    use_case = LogoutUseCase(FakeSessionRepository(), FakeJWTService())

    await use_case.execute(None)  # no debe lanzar — el objetivo es dejar al usuario fuera


@pytest.mark.asyncio
async def test_logout_with_undecodable_token_does_not_raise():
    class RaisingJWTService(FakeJWTService):
        def verify_token(self, token: str) -> dict:
            raise ValueError("token expirado o corrupto")

    use_case = LogoutUseCase(FakeSessionRepository(), RaisingJWTService())

    await use_case.execute("garbage-token")


@pytest.mark.asyncio
async def test_logout_with_undecodable_token_logs_the_failure_at_debug_level():
    """Bug real (auditoría QA): el fallo quedaba en silencio total — ni
    siquiera un log para investigar un cliente mandando tokens corruptos de
    forma sistemática. Mismo patrón que `AuthMiddleware` (`error_type`)."""

    class RaisingJWTService(FakeJWTService):
        def verify_token(self, token: str) -> dict:
            raise ValueError("token expirado o corrupto")

    use_case = LogoutUseCase(FakeSessionRepository(), RaisingJWTService())

    with patch("src.features.auth.application.use_cases.logout.logger") as mock_logger:
        await use_case.execute("garbage-token")

    mock_logger.debug.assert_called_once()
    _, kwargs = mock_logger.debug.call_args
    assert kwargs["error_type"] == "ValueError"
