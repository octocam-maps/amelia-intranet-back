from datetime import datetime, timezone

import pytest

from src.features.auth.application.use_cases.logout_all_sessions import (
    LogoutAllSessionsUseCase,
)

from .fakes import FakeSessionRepository


@pytest.mark.asyncio
async def test_logout_all_revokes_every_active_session_of_the_user_only():
    session_repo = FakeSessionRepository()
    now = datetime.now(timezone.utc)
    await session_repo.create_session(
        user_id="user-1", jti="a", family_id="fam-1", expires_at=now, user_agent=None, ip_address=None
    )
    await session_repo.create_session(
        user_id="user-1", jti="b", family_id="fam-2", expires_at=now, user_agent=None, ip_address=None
    )
    await session_repo.create_session(
        user_id="user-2", jti="c", family_id="fam-3", expires_at=now, user_agent=None, ip_address=None
    )

    use_case = LogoutAllSessionsUseCase(session_repo)
    revoked_count = await use_case.execute("user-1")

    assert revoked_count == 2
    assert session_repo.sessions["a"]["revoked"] is True
    assert session_repo.sessions["b"]["revoked"] is True
    assert session_repo.sessions["c"]["revoked"] is False  # otro usuario, no debe tocarse
