"""
Test route-level (SOFT-2170): reproduce el bug real detectado en el E2E de
Fase 1 — con `REFRESH_TOKEN_COOKIE_PATH=/auth/refresh`, el navegador (y el
cookie jar de `httpx`/`TestClient`, que respeta `path` igual que un
navegador real) NUNCA mandaba la cookie a `POST /auth/logout`, así que
`LogoutUseCase` recibía `None` y no revocaba nada server-side.

Se ejercitan las rutas reales de FastAPI (no los casos de uso a pelo) para
probar justo la parte que falló: que la cookie emitida por `/auth/login`
efectivamente viaje hasta `/auth/logout` dentro del mismo `path`. Se
sustituyen `IUserRepository`/`ISessionRepository`/`IGoogleIdentityVerifier`
por fakes vía `app.dependency_overrides` (sin Postgres ni Google reales);
el `JWTService` SÍ es el real (compartido con `get_current_user`), para que
el access_token emitido en el login sea uno que la propia app pueda
verificar de vuelta.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")
# `main.load_dotenv()` NO sobreescribe variables ya presentes en el entorno
# (`override=False` por defecto) — fijamos esto aquí para que el test no
# dependa de lo que tenga el `.env` real del repo (que puede seguir con el
# valor viejo `/auth/refresh` hasta que se actualice manualmente).
os.environ.setdefault("REFRESH_TOKEN_COOKIE_PATH", "/auth")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.auth.application.tests.fakes import (  # noqa: E402
    FakeGoogleIdentity,
    FakeGoogleVerifier,
    FakeSessionRepository,
    FakeUserRepository,
)
from src.features.auth.application.use_cases.login_with_google import (  # noqa: E402
    LoginWithGoogleUseCase,
)
from src.features.auth.application.use_cases.logout import LogoutUseCase  # noqa: E402
from src.features.auth.application.use_cases.refresh_session import (  # noqa: E402
    RefreshSessionUseCase,
)
from src.features.auth.infrastructure import dependencies as auth_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _override_auth_dependencies() -> FakeSessionRepository:
    """Sustituye BD/Google por fakes; el JWTService es el real y compartido
    con `get_current_user`, para que los tokens emitidos en login sean
    verificables por el resto de la app sin duplicar la firma."""
    identity = FakeGoogleIdentity(
        sub="google-sub-1",
        email="empleado@ameliahub.com",
        email_verified=True,
        full_name="Empleado de Prueba",
        avatar_url=None,
        hosted_domain="ameliahub.com",
        is_internal=True,
    )
    user_repo = FakeUserRepository()
    session_repo = FakeSessionRepository()
    jwt_service = get_jwt_service()
    google_verifier = FakeGoogleVerifier(identity)

    app.dependency_overrides[auth_dependencies.get_login_with_google_use_case] = (
        lambda: LoginWithGoogleUseCase(user_repo, session_repo, google_verifier, jwt_service)
    )
    app.dependency_overrides[auth_dependencies.get_refresh_session_use_case] = (
        lambda: RefreshSessionUseCase(user_repo, session_repo, jwt_service)
    )
    app.dependency_overrides[auth_dependencies.get_logout_use_case] = (
        lambda: LogoutUseCase(session_repo, jwt_service)
    )
    return session_repo


def test_logout_revokes_session_now_that_the_cookie_reaches_the_route():
    session_repo = _override_auth_dependencies()
    try:
        with TestClient(app) as client:
            login_response = client.post("/auth/login", json={"id_token": "fake-id-token"})
            assert login_response.status_code == 200
            access_token = login_response.json()["access_token"]

            set_cookie_header = login_response.headers.get("set-cookie", "").lower()
            assert "path=/auth" in set_cookie_header
            assert "path=/auth/refresh" not in set_cookie_header  # el bug: path viejo

            assert len(session_repo.sessions) == 1
            assert all(not s["revoked"] for s in session_repo.sessions.values())

            logout_response = client.post(
                "/auth/logout", headers={"Authorization": f"Bearer {access_token}"}
            )
            assert logout_response.status_code == 204

            # Antes del fix (path=/auth/refresh) la cookie no llegaba aquí y
            # esta aserción fallaba: la sesión quedaba activa para siempre.
            assert all(s["revoked"] for s in session_repo.sessions.values())
    finally:
        app.dependency_overrides.clear()


def test_refresh_still_works_under_the_new_cookie_path():
    _override_auth_dependencies()
    try:
        with TestClient(app) as client:
            client.post("/auth/login", json={"id_token": "fake-id-token"})

            refresh_response = client.post("/auth/refresh")

            assert refresh_response.status_code == 200
            assert "access_token" in refresh_response.json()
    finally:
        app.dependency_overrides.clear()
