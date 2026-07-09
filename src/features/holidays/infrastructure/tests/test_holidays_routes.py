"""
Test route-level: "Festivos" solo aparece en la sección "Administración"
del admin para escribir; el externo-invitado NO tiene "Ausencias" en la
matriz de permisos (❌) y debe rechazarse en el BACKEND. Mismo patrón que
`features/absences/infrastructure/tests/test_absences_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.holidays.infrastructure import dependencies as holidays_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {
            "sub": "user-1",
            "email": "user@ameliahub.com",
            "role": role,
            "entity_id": None,
            "is_external": role == "externo_invitado",
        }
    )


def test_externo_invitado_cannot_list_holidays():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/holidays",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_can_list_holidays_but_not_write():
    class FakeListUseCase:
        async def execute(self, *, year=None, entity_code=None):
            return []

    app.dependency_overrides[holidays_dependencies.get_list_holidays_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_token_for('empleado')}"}
            list_response = client.get("/holidays", headers=headers)
            create_response = client.post(
                "/holidays", json={"day": "2026-12-25", "name": "Navidad"}, headers=headers
            )
            delete_response = client.delete("/holidays/hol-1", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json() == {"holidays": []}
    assert create_response.status_code == 403
    assert delete_response.status_code == 403


def test_admin_can_create_a_holiday():
    class FakeCreateUseCase:
        async def execute(self, *, day, name, entity_code, scope=None):
            class _Holiday:
                id = "hol-1"
                pass

            h = _Holiday()
            h.day = day
            h.name = name
            h.entity_id = None
            h.entity_code = entity_code
            h.created_at = "2026-07-09T09:14:00Z"
            h.updated_at = "2026-07-09T09:14:00Z"
            h.source = "manual"
            h.scope = None
            return h

    app.dependency_overrides[holidays_dependencies.get_create_holiday_use_case] = (
        lambda: FakeCreateUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/holidays",
                json={"day": "2026-12-25", "name": "Navidad"},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 201
            assert response.json()["name"] == "Navidad"
    finally:
        app.dependency_overrides.clear()
