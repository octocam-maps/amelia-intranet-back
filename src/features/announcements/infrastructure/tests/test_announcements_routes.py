"""
Test route-level: "Anuncios" solo aparece en la sección "Administración" del
admin y en el dashboard del empleado (docs/permisos-roles.md) — el
externo-invitado NO tiene "Inicio" en su navbar (❌) y debe rechazarse en el
BACKEND. Solo el admin puede crear/editar/borrar. Mismo patrón que
`features/mailbox/infrastructure/tests/test_mailbox_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.announcements.infrastructure import dependencies as announcements_dependencies  # noqa: E402
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


def test_externo_invitado_cannot_list_announcements():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/announcements",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_can_list_the_feed():
    class FakeListUseCase:
        async def execute(self, *, requester_role, requester_entity_id, limit=None):
            return []

    app.dependency_overrides[announcements_dependencies.get_list_announcements_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/announcements",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
            assert response.status_code == 200
            assert response.json() == {"announcements": []}
    finally:
        app.dependency_overrides.clear()


def test_empleado_cannot_create_edit_or_delete_announcements():
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_token_for('empleado')}"}
            create_response = client.post(
                "/announcements",
                json={"title": "t", "body": "b"},
                headers=headers,
            )
            update_response = client.patch(
                "/announcements/ann-1", json={"title": "t"}, headers=headers
            )
            delete_response = client.delete("/announcements/ann-1", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 403
    assert update_response.status_code == 403
    assert delete_response.status_code == 403


def test_admin_can_create_an_announcement():
    class FakeCreateUseCase:
        async def execute(self, **kwargs):
            class _Announcement:
                id = "ann-1"
                title = kwargs["title"]
                body = kwargs["body"]
                author_id = kwargs["author_id"]
                author_full_name = "Beatriz Luna"
                audience = kwargs["audience"]
                entity_id = None
                entity_code = None
                role_id = None
                role_code = None
                is_pinned = kwargs["is_pinned"]
                published_at = "2026-07-09T09:14:00Z"
                created_at = "2026-07-09T09:14:00Z"
                updated_at = "2026-07-09T09:14:00Z"

            return _Announcement()

    app.dependency_overrides[announcements_dependencies.get_create_announcement_use_case] = (
        lambda: FakeCreateUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/announcements",
                json={"title": "Comunicado", "body": "cuerpo"},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 201
            assert response.json()["title"] == "Comunicado"
    finally:
        app.dependency_overrides.clear()
