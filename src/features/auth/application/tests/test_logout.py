from datetime import datetime, timezone

import pytest

from src.features.auth.application.use_cases.logout import LogoutUseCase

from .fakes import FakeJWTService, FakeSessionRepository


@pytest.mark.asyncio
async def test_logout_revokes_current_session():
    session_repo = FakeSessionRepository()
    await session_repo.create_session(
        user_id="user-1", jti="jti-1", expires_at=datetime.now(timezone.utc), user_agent=None, ip_address=None
    )
    use_case = LogoutUseCase(session_repo, FakeJWTService())

    await use_case.execute("refresh:user-1:jti-1")

    assert session_repo.sessions["jti-1"]["revoked"] is True


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
