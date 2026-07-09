"""
Test route-level: el externo-invitado NO tiene "Control horario" en la
matriz de permisos (docs/permisos-roles.md: ❌) — debe rechazarse en el
BACKEND, no solo ocultarse del navbar. Se ejercitan las rutas reales de
FastAPI (mismo patrón que `features/auth/infrastructure/tests/test_auth_routes.py`):
el `JWTService` es el real (comparte secreto con `get_current_user`), solo
se sustituye el repositorio por un fake vía `app.dependency_overrides`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.time_clock.infrastructure import dependencies as time_clock_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {"sub": "user-1", "email": "user@ameliahub.com", "role": role, "entity_id": None, "is_external": role == "externo_invitado"}
    )


def test_externo_invitado_cannot_list_time_clock_entries():
    response = None
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries", headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_employee_can_list_their_own_time_clock_entries():
    class FakeListUseCase:
        async def execute(self, **kwargs):
            return []

    app.dependency_overrides[time_clock_dependencies.get_list_time_clock_entries_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
            assert response.status_code == 200
            assert response.json() == {"entries": []}
    finally:
        app.dependency_overrides.clear()
