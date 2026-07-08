import asyncio
from datetime import datetime, timezone

import pytest

from src.features.auth.application.results import RefreshResult
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
        user_id="user-1",
        jti="jti-1",
        family_id="fam-1",
        expires_at=datetime.now(timezone.utc),
        user_agent=None,
        ip_address=None,
    )

    use_case = RefreshSessionUseCase(user_repo, session_repo, FakeJWTService())
    result = await use_case.execute("refresh:user-1:jti-1")

    assert result.access_token == "access:user-1"
    assert session_repo.sessions["jti-1"]["revoked"] is True  # jti viejo, revocado
    assert len(session_repo.sessions) == 2  # se creó una sesión nueva (rotación)
    new_jti = next(jti for jti in session_repo.sessions if jti != "jti-1")
    assert session_repo.sessions[new_jti]["family_id"] == "fam-1"  # misma familia


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


@pytest.mark.asyncio
async def test_reuse_of_already_rotated_jti_revokes_entire_family():
    """
    Patrón OWASP: reusar un jti ya rotado es la señal de que un refresh
    token fue robado y copiado. La respuesta correcta no es solo rechazar
    ese jti puntual — hay que matar TODA la familia (incluido el
    descendiente legítimo que la rotación ya haya creado), porque no
    sabemos cuál de las dos partes (víctima o atacante) usó cuál copia.
    """
    user_repo = FakeUserRepository(users=[_active_user()])
    session_repo = FakeSessionRepository()

    use_case = RefreshSessionUseCase(user_repo, session_repo, FakeJWTService())

    await session_repo.create_session(
        user_id="user-1",
        jti="jti-1",
        family_id="fam-1",
        expires_at=datetime.now(timezone.utc),
        user_agent=None,
        ip_address=None,
    )

    # Refresh legítimo: rota jti-1 -> jti-2 (misma familia).
    await use_case.execute("refresh:user-1:jti-1")
    assert any(not s["revoked"] for s in session_repo.sessions.values())  # jti-2 sigue activo

    # Alguien reusa la copia vieja del refresh token (jti-1, ya revocado).
    with pytest.raises(InvalidTokenError):
        await use_case.execute("refresh:user-1:jti-1")

    # Toda la familia (jti-1 Y jti-2) queda revocada — 0 sesiones activas.
    assert all(s["revoked"] for s in session_repo.sessions.values())
    assert not any(not s["revoked"] for s in session_repo.sessions.values())


@pytest.mark.asyncio
async def test_concurrent_refresh_with_same_jti_never_leaves_more_than_one_active():
    """
    Simula dos llamadas "casi simultáneas" con el MISMO refresh token — el
    escenario que el single-flight del frontend debe evitar en primer
    lugar. Como defensa en profundidad, el backend nunca debe terminar con
    más de una sesión activa en la familia: la primera rota con éxito: la
    segunda, al encontrar el jti ya revocado, dispara la detección de reuso
    y revoca la familia entera (0 activas) en vez de dejar dos cadenas
    vivas en paralelo.
    """
    user_repo = FakeUserRepository(users=[_active_user()])
    session_repo = FakeSessionRepository()
    await session_repo.create_session(
        user_id="user-1",
        jti="jti-1",
        family_id="fam-1",
        expires_at=datetime.now(timezone.utc),
        user_agent=None,
        ip_address=None,
    )

    use_case = RefreshSessionUseCase(user_repo, session_repo, FakeJWTService())

    results = await asyncio.gather(
        use_case.execute("refresh:user-1:jti-1"),
        use_case.execute("refresh:user-1:jti-1"),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, RefreshResult)]
    failures = [r for r in results if isinstance(r, BaseException)]
    active_sessions = [s for s in session_repo.sessions.values() if not s["revoked"]]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], InvalidTokenError)
    assert len(active_sessions) <= 1
