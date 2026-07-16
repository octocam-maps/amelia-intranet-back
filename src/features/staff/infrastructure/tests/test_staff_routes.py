"""
Test route-level: "Gestión de plantilla" es una función exclusiva del
admin (docs/permisos-roles.md § "Sección Administración") — empleado y
externo-invitado deben rechazarse en el BACKEND, no solo no ver el ítem en
el navbar. Mismo patrón que
`features/absences/infrastructure/tests/test_absences_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.staff.infrastructure import dependencies as staff_dependencies  # noqa: E402
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


def test_empleado_cannot_list_staff():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/staff", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_create_staff_member():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/staff",
                json={
                    "full_name": "Sandra Ramírez",
                    "email": "sandra@ameliahub.com",
                    "entity": "hub",
                    "role": "empleado",
                },
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_cannot_patch_staff_member():
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/staff/user-1",
                json={"is_active": False},
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_patch_a_staff_members_role_to_socio_and_back():
    """`RoleCode` [migración 024] admite `socio` en `PATCH /staff/{id}` —
    sin esto, guardar la ficha de un socio desde "Plantilla" por CUALQUIER
    motivo (p. ej. cambiar el puesto) mandaría el rol pre-cargado del
    formulario y, si el backend rechazara `socio` con 422, el frontend no
    podría ni mostrar ni conservar el rol al reenviarlo tal cual."""
    from datetime import datetime, timezone

    from src.features.staff.domain.entities import StaffMember

    received_role_codes = []

    class FakeUpdateUseCase:
        async def execute(self, user_id, **kwargs):
            received_role_codes.append(kwargs["role_code"])
            return StaffMember(
                id=user_id,
                full_name="David Ferre",
                email="david@octocam-maps.com",
                avatar_url=None,
                job_title="Socio",
                department_id=None,
                department_name=None,
                entity_id=None,
                entity_code=None,
                role_id="role-socio",
                role_code=kwargs["role_code"] or "socio",
                status="active",
                hire_date=None,
                vacation_days_per_year=None,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    app.dependency_overrides[staff_dependencies.get_update_staff_member_use_case] = (
        lambda: FakeUpdateUseCase()
    )
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_token_for('administrador')}"}
            response = client.patch(
                "/staff/user-david", json={"role": "socio"}, headers=headers
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["role_code"] == "socio"
    assert received_role_codes == ["socio"]


def test_admin_can_list_staff():
    class FakeListUseCase:
        async def execute(self, *, entity_code, search, page, page_size):
            return [], 0

    app.dependency_overrides[staff_dependencies.get_list_staff_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/staff", headers={"Authorization": f"Bearer {_token_for('administrador')}"}
            )
            assert response.status_code == 200
            assert response.json() == {"members": [], "total": 0}
    finally:
        app.dependency_overrides.clear()
