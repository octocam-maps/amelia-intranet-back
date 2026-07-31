"""
Test route-level: `/email-templates` es ADMIN_ONLY entero. Quien edita estas
plantillas escribe el texto que la intranet manda EN NOMBRE de la empresa a toda
la plantilla — misma superficie de confianza que "Anuncios", no la de un ajuste
personal.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent"
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.email_templates.infrastructure import dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402

from ...application.tests.fakes import build_template  # noqa: E402


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


@pytest.mark.parametrize(
    "role", ["empleado", "socio", "becario", "externo_invitado"]
)
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/email-templates"),
        ("patch", "/email-templates/staff_invited"),
        ("post", "/email-templates/staff_invited/restore"),
        ("post", "/email-templates/staff_invited/preview"),
    ],
)
def test_only_the_admin_can_reach_the_email_templates(role, method, path):
    # `client.get()` no admite `json` — solo se manda cuerpo en los verbos que lo
    # llevan.
    kwargs = {"headers": {"Authorization": f"Bearer {_token_for(role)}"}}
    if method != "get":
        kwargs["json"] = {"subject": "x", "body": "x"}
    try:
        with TestClient(app) as client:
            response = getattr(client, method)(path, **kwargs)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403, f"{role} alcanzó {method.upper()} {path}"


def test_the_list_ships_the_available_placeholders():
    """La lista blanca real vive en `render_placeholders`. Se manda desde el
    backend para que la ayuda de la pantalla no se desincronice del
    comportamiento en el primer placeholder que se añada."""

    class FakeUseCase:
        async def execute(self):
            return [build_template()]

    app.dependency_overrides[dependencies.get_list_email_templates_use_case] = (
        lambda: FakeUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/email-templates",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "full_name" in body["available_placeholders"]
    assert body["templates"][0]["template_key"] == "staff_invited"


def test_preview_returns_the_rendered_subject_and_html():
    class FakeUseCase:
        async def execute(self, template_key, *, subject=None, body=None):
            assert subject == "Hola {{full_name}}"
            return "Hola Ana Ejemplo", "<html><body>ok</body></html>"

    app.dependency_overrides[dependencies.get_preview_email_template_use_case] = (
        lambda: FakeUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/email-templates/staff_invited/preview",
                json={"subject": "Hola {{full_name}}"},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["subject"] == "Hola Ana Ejemplo"


def test_an_empty_subject_is_rejected_by_the_dto_with_422():
    """Defensa en el borde además de en el caso de uso: `min_length=1` corta antes
    de llegar al dominio."""
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/email-templates/staff_invited",
                json={"subject": "", "body": "x"},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_there_is_no_endpoint_to_create_a_template():
    """El catálogo es CERRADO: una fila nueva no haría aparecer un correo nuevo,
    así que permitir crearlas lo sugeriría en falso."""
    try:
        with TestClient(app) as client:
            response = client.post(
                "/email-templates",
                json={
                    "template_key": "inventada",
                    "subject": "x",
                    "body": "x",
                },
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 405
