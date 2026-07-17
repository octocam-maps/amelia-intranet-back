"""
Test route-level: `GET /roles` es exclusivo del admin — hoy es el único
consumidor real (`StaffForm`, "Plantilla"). Mismo patrón que
`features/staff/infrastructure/tests/test_staff_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.roles.domain.entities import Role  # noqa: E402
from src.features.roles.infrastructure import dependencies as roles_dependencies  # noqa: E402
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


def test_empleado_cannot_list_roles():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/roles", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_socio_cannot_list_roles():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/roles", headers={"Authorization": f"Bearer {_token_for('socio')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_list_all_four_roles():
    class FakeListRolesUseCase:
        async def execute(self):
            return [
                Role(id="role-1", code="administrador", name="Administrador"),
                Role(id="role-2", code="empleado", name="Empleado"),
                Role(id="role-3", code="externo_invitado", name="Externo-invitado"),
                Role(id="role-4", code="socio", name="Socio"),
            ]

    app.dependency_overrides[roles_dependencies.get_list_roles_use_case] = (
        lambda: FakeListRolesUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/roles",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    codes = {role["code"] for role in body["roles"]}
    assert codes == {"administrador", "empleado", "externo_invitado", "socio"}
    assert {role["name"] for role in body["roles"]} == {
        "Administrador",
        "Empleado",
        "Externo-invitado",
        "Socio",
    }
