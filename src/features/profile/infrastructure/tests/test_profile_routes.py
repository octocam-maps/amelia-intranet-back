"""
Test route-level: "Mi perfil" es de solo lectura y accesible por los 3
roles del producto, pero SIEMPRE resuelto por `current_user["sub"]` (RGPD:
cada usuario solo ve su propio perfil, nunca por id de la URL). Mismo
patrón que `features/staff/infrastructure/tests/test_staff_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from datetime import date  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.profile.domain.entities import UserProfile  # noqa: E402
from src.features.profile.domain.errors import ProfileNotFoundError  # noqa: E402
from src.features.profile.infrastructure import dependencies as profile_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str, *, sub: str = "user-1") -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {
            "sub": sub,
            "email": "user@ameliahub.com",
            "role": role,
            "entity_id": None,
            "is_external": role == "externo_invitado",
        }
    )


def _profile() -> UserProfile:
    return UserProfile(
        id="user-1",
        email="sandra@ameliahub.com",
        full_name="Sandra Ramírez",
        avatar_url="https://example.com/avatar.png",
        role_code="empleado",
        job_title="Project Manager",
        hire_date=date(2022, 3, 1),
        entity_name="Amelia Hub",
        department_name="Operaciones",
        manager_name="Beatriz Luna",
        is_external=False,
    )


def test_get_my_profile_returns_the_requesting_users_profile():
    class FakeGetMyProfileUseCase:
        async def execute(self, user_id: str):
            assert user_id == "user-1"
            return _profile()

    app.dependency_overrides[profile_dependencies.get_my_profile_use_case] = (
        lambda: FakeGetMyProfileUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/profile/me",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": "user-1",
        "email": "sandra@ameliahub.com",
        "full_name": "Sandra Ramírez",
        "avatar_url": "https://example.com/avatar.png",
        "role": "empleado",
        "job_title": "Project Manager",
        "hire_date": "2022-03-01",
        "entity_name": "Amelia Hub",
        "department_name": "Operaciones",
        "manager_name": "Beatriz Luna",
        "is_external": False,
    }


def test_get_my_profile_ignores_any_id_and_always_uses_the_token_subject():
    """RGPD: el endpoint no acepta ni recibe ningún id de la URL/query — solo
    existe `user_id = current_user["sub"]`. Este test fija que el use case
    siempre se llama con el `sub` del token, no con nada externo."""

    received_ids = []

    class FakeGetMyProfileUseCase:
        async def execute(self, user_id: str):
            received_ids.append(user_id)
            return _profile()

    app.dependency_overrides[profile_dependencies.get_my_profile_use_case] = (
        lambda: FakeGetMyProfileUseCase()
    )
    token = _token_for("administrador", sub="admin-42")
    try:
        with TestClient(app) as client:
            client.get("/profile/me", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert received_ids == ["admin-42"]


def test_externo_invitado_can_read_its_own_profile():
    class FakeGetMyProfileUseCase:
        async def execute(self, user_id: str):
            return UserProfile(
                id="user-3",
                email="externo@example.com",
                full_name="Carla Externa",
                avatar_url=None,
                role_code="externo_invitado",
                job_title=None,
                hire_date=None,
                entity_name=None,
                department_name=None,
                manager_name=None,
                is_external=True,
            )

    app.dependency_overrides[profile_dependencies.get_my_profile_use_case] = (
        lambda: FakeGetMyProfileUseCase()
    )
    token = _token_for("externo_invitado", sub="user-3")
    try:
        with TestClient(app) as client:
            response = client.get("/profile/me", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "externo_invitado"
    assert body["is_external"] is True
    assert body["entity_name"] is None
    assert body["manager_name"] is None


def test_requires_authentication():
    with TestClient(app) as client:
        response = client.get("/profile/me")

    assert response.status_code in (401, 403)


def test_get_my_profile_propagates_not_found_when_user_has_no_profile():
    class FakeGetMyProfileUseCase:
        async def execute(self, user_id: str):
            raise ProfileNotFoundError("No se encontró el perfil del usuario.")

    app.dependency_overrides[profile_dependencies.get_my_profile_use_case] = (
        lambda: FakeGetMyProfileUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/profile/me",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
