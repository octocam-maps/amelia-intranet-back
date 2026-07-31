"""
`GET /manuals` — "que todos los usuarios de la plataforma puedan utilizarlo".

Es el requisito literal del endpoint, así que el test lo recorre rol por rol: si
alguien restringe esto más adelante, salta aquí.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent"
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.onboarding.infrastructure import dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402

from ...application.tests.steps import (  # noqa: E402
    CLICKUP_MANUAL_DOCUMENT,
    LIBRARY_MANUAL_DOCUMENT,
)


def _token_for(role: str) -> str:
    return get_jwt_service().create_access_token(
        {
            "sub": "user-1",
            "email": "user@ameliahub.com",
            "role": role,
            "entity_id": None,
            "is_external": role == "externo_invitado",
        }
    )


class FakeUseCase:
    async def execute(self, *, user_id):
        return [(CLICKUP_MANUAL_DOCUMENT, True), (LIBRARY_MANUAL_DOCUMENT, False)]


@pytest.mark.parametrize(
    "role", ["administrador", "empleado", "socio", "becario", "externo_invitado"]
)
def test_every_role_can_read_the_manuals_library(role):
    """Los CINCO roles, incluido el externo-invitado: su onboarding parcial ya era
    vídeo + manuales, así que los manuales nunca fueron material restringido."""
    app.dependency_overrides[dependencies.get_list_manuals_library_use_case] = (
        lambda: FakeUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/manuals", headers={"Authorization": f"Bearer {_token_for(role)}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, f"{role} no pudo leer la biblioteca"
    assert len(response.json()["manuals"]) == 2


def test_it_still_requires_being_logged_in():
    """"Todos los usuarios" son los de la plataforma, no el mundo entero: los
    manuales son material corporativo interno."""
    try:
        with TestClient(app) as client:
            response = client.get("/manuals")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code in (401, 403)


def test_the_response_distinguishes_required_from_consultation_manuals():
    app.dependency_overrides[dependencies.get_list_manuals_library_use_case] = (
        lambda: FakeUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/manuals",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    manuals = response.json()["manuals"]
    assert manuals[0]["required_in_onboarding"] is True
    assert manuals[0]["acknowledged"] is True
    assert manuals[1]["required_in_onboarding"] is False


def test_the_content_hash_is_never_exposed():
    """Es el registro de integridad interno (RNF2.2), no algo que el cliente
    necesite — mismo criterio que el resto de los DTO de documento."""
    app.dependency_overrides[dependencies.get_list_manuals_library_use_case] = (
        lambda: FakeUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/manuals",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert "content_hash" not in response.text
