"""
Smoke test: la app debe levantar y responder aunque la base de datos no esté
disponible (el lifespan solo loguea un warning, no aborta el arranque —
así el health check de un orquestador no depende de Postgres).
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


def test_health_check_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_root_ok():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "amelia-intranet-back"


def test_protected_route_without_token_is_rejected():
    with TestClient(app) as client:
        response = client.get("/auth/me")

    assert response.status_code == 401


def test_login_with_missing_body_is_validation_error():
    with TestClient(app) as client:
        response = client.post("/auth/login", json={})

    assert response.status_code == 422
