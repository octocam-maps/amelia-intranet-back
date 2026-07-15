"""
Test route-level: `quiz`, `sign` y `complete-profile` son exclusivos de
roles internos — el externo-invitado debe rechazarse en el BACKEND
(403), no solo ocultarse del navbar. `video-progress` y `acknowledge` sí
están abiertos al externo-invitado (onboarding parcial). Mismo patrón que
`features/absences/infrastructure/tests/test_absences_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent"
)

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

from src.features.onboarding.infrastructure import (
    dependencies as onboarding_dependencies,  # noqa: E402
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


def test_externo_invitado_cannot_submit_quiz():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-quiz/quiz",
                json={"answers": {"q1": "7"}},
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_sign():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-signature/sign",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_complete_profile():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-profile/complete-profile",
                json={},
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_can_reach_get_me():
    class FakeGetMyOnboardingUseCase:
        async def execute(self, *, user_id, role):
            return []

    app.dependency_overrides[onboarding_dependencies.get_my_onboarding_use_case] = (
        lambda: FakeGetMyOnboardingUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/onboarding/me",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
            assert response.status_code == 200
            assert response.json() == {"steps": []}
    finally:
        app.dependency_overrides.clear()


def test_unauthenticated_request_is_rejected():
    try:
        with TestClient(app) as client:
            response = client.get("/onboarding/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
