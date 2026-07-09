"""
Test route-level: el externo-invitado NO tiene "Buzón anónimo" en la matriz
de permisos (docs/permisos-roles.md: ❌) y el empleado solo puede ENVIAR
(👁️), nunca abrir la recepción — debe rechazarse en el BACKEND. Mismo
patrón que `features/absences/infrastructure/tests/test_absences_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.mailbox.infrastructure import dependencies as mailbox_dependencies  # noqa: E402
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


def test_externo_invitado_cannot_submit_a_message():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/mailbox/messages",
                json={"category": "sugerencia", "body": "hola"},
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_cannot_open_the_reception_tray():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/mailbox/messages",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_can_submit_a_message_and_only_gets_a_reference_code_back():
    class FakeSubmitUseCase:
        async def execute(self, *, category, subject, body):
            class _Message:
                reference_code = "ABCDEF123456"

            return _Message()

    app.dependency_overrides[mailbox_dependencies.get_submit_anonymous_message_use_case] = (
        lambda: FakeSubmitUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/mailbox/messages",
                json={"category": "sugerencia", "body": "¿Habrá plazas de parking?"},
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
            assert response.status_code == 201
            # Solo el reference_code — nada que identifique al emisor vuelve
            # en la respuesta.
            assert response.json() == {"reference_code": "ABCDEF123456"}
    finally:
        app.dependency_overrides.clear()


def test_admin_can_open_the_reception_tray():
    class FakeListUseCase:
        async def execute(self, *, status_filter):
            return []

    app.dependency_overrides[mailbox_dependencies.get_list_mailbox_messages_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/mailbox/messages",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 200
            assert response.json() == {"messages": []}
    finally:
        app.dependency_overrides.clear()


def test_empleado_cannot_reply_or_resolve():
    try:
        with TestClient(app) as client:
            reply_response = client.post(
                "/mailbox/messages/msg-1/reply",
                json={"admin_reply": "hola"},
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
            resolve_response = client.post(
                "/mailbox/messages/msg-1/resolve",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert reply_response.status_code == 403
    assert resolve_response.status_code == 403


def test_track_endpoint_does_not_require_authentication():
    """El seguimiento anónimo NO puede exigir un token — eso ataría el
    seguimiento a una identidad y rompería el anonimato por diseño."""

    class FakeTrackUseCase:
        async def execute(self, *, reference_code):
            class _Message:
                reference_code = "ABCDEF123456"
                category = "sugerencia"
                subject = None
                body = "cuerpo"
                status = "new"
                admin_reply = None
                created_at = "2026-07-09T09:14:00Z"

            return _Message()

    app.dependency_overrides[mailbox_dependencies.get_track_message_use_case] = (
        lambda: FakeTrackUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get("/mailbox/track/ABCDEF123456")
            assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
