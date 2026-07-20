"""
Test route-level: `GET /departments` acepta a los roles internos con
onboarding completo (`administrador`, `empleado`, `socio`) y rechaza al
externo-invitado. Mismo patrón que
`features/roles/infrastructure/tests/test_roles_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.departments.domain.entities import Department  # noqa: E402
from src.features.departments.infrastructure import (  # noqa: E402
    dependencies as departments_dependencies,
)
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


class _FakeListDepartmentsUseCase:
    async def execute(self):
        return [
            Department(
                id="dept-1", name="Recursos Humanos", entity_id="entity-hub", entity_code="hub"
            ),
            Department(
                id="dept-2", name="Operaciones", entity_id="entity-ops", entity_code="ops"
            ),
        ]


def test_externo_invitado_cannot_list_departments():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/departments",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_can_list_departments():
    app.dependency_overrides[departments_dependencies.get_list_departments_use_case] = (
        lambda: _FakeListDepartmentsUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/departments",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    names = {department["name"] for department in body["departments"]}
    assert names == {"Recursos Humanos", "Operaciones"}


def test_socio_can_list_departments():
    app.dependency_overrides[departments_dependencies.get_list_departments_use_case] = (
        lambda: _FakeListDepartmentsUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/departments",
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_admin_can_list_departments():
    app.dependency_overrides[departments_dependencies.get_list_departments_use_case] = (
        lambda: _FakeListDepartmentsUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/departments",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
