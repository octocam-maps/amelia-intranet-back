"""
Test route-level: el externo-invitado NO tiene "Ausencias" en la matriz de
permisos (docs/permisos-roles.md: ❌) — debe rechazarse en el BACKEND, no
solo ocultarse del navbar. Mismo patrón que
`features/time_clock/infrastructure/tests/test_time_clock_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.absences.infrastructure import dependencies as absences_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {"sub": "user-1", "email": "user@ameliahub.com", "role": role, "entity_id": None, "is_external": role == "externo_invitado"}
    )


def test_externo_invitado_cannot_list_absence_types():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/types", headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_open_pending_tray():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/requests/pending",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_employee_can_list_absence_types():
    class FakeListTypesUseCase:
        async def execute(self):
            return []

    app.dependency_overrides[absences_dependencies.get_list_absence_types_use_case] = (
        lambda: FakeListTypesUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/types", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
            assert response.status_code == 200
            assert response.json() == {"types": []}
    finally:
        app.dependency_overrides.clear()


def test_employee_cannot_open_pending_tray():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/requests/pending",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
