"""
Test route-level: la gestión de invitaciones es exclusiva del admin
(docs/permisos-roles.md § "Gestión de plantilla") — empleado y
externo-invitado deben rechazarse en el BACKEND, no solo no ver el ítem en
el navbar. Mismo patrón que
`features/staff/infrastructure/tests/test_staff_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.invitations.domain.entities import Invitation  # noqa: E402
from src.features.invitations.infrastructure import dependencies as invitations_dependencies  # noqa: E402
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


def _fake_invitation() -> Invitation:
    now = datetime.now(timezone.utc)
    return Invitation(
        id="inv-1",
        email="sandra@ameliahub.com",
        full_name="Sandra Ramírez",
        role_id="role-empleado",
        role_code="empleado",
        entity_id="entity-hub",
        entity_code="hub",
        invited_by_name="Beatriz Luna",
        status="pending",
        expires_at=now + timedelta(days=7),
        created_at=now,
    )


def test_empleado_cannot_list_invitations():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/invitations", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_resend_invitation():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/invitations/inv-1/resend",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_socio_cannot_cancel_invitation():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/invitations/inv-1/cancel",
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_list_pending_invitations():
    class FakeListUseCase:
        async def execute(self, *, status=None):
            assert status == "pending"
            return [_fake_invitation()]

    app.dependency_overrides[invitations_dependencies.get_list_invitations_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/invitations?status=pending",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body["invitations"]) == 1
    assert body["invitations"][0]["email"] == "sandra@ameliahub.com"


def test_admin_can_resend_invitation():
    class FakeResendUseCase:
        async def execute(self, invitation_id):
            assert invitation_id == "inv-1"
            return _fake_invitation()

    app.dependency_overrides[invitations_dependencies.get_resend_invitation_use_case] = (
        lambda: FakeResendUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/invitations/inv-1/resend",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == "inv-1"


def test_admin_can_cancel_invitation():
    class FakeCancelUseCase:
        async def execute(self, invitation_id):
            assert invitation_id == "inv-1"
            now = datetime.now(timezone.utc)
            return Invitation(
                id="inv-1",
                email="sandra@ameliahub.com",
                full_name="Sandra Ramírez",
                role_id="role-empleado",
                role_code="empleado",
                entity_id="entity-hub",
                entity_code="hub",
                invited_by_name="Beatriz Luna",
                status="revoked",
                expires_at=now + timedelta(days=7),
                created_at=now,
            )

    app.dependency_overrides[invitations_dependencies.get_cancel_invitation_use_case] = (
        lambda: FakeCancelUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/invitations/inv-1/cancel",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
