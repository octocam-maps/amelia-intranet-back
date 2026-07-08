import os
import time

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from src.shared.errors.base import InvalidTokenError, TokenExpiredError  # noqa: E402
from src.shared.jwt.infrastructure.jwt_service import JWTService  # noqa: E402


@pytest.fixture
def jwt_service():
    # `JWTService.__new__` devuelve el singleton de clase; forzamos que
    # `__init__` vuelva a correr (en vez de hacer early-return por
    # `_initialized`) para aislar cada test de los demás.
    service = JWTService.__new__(JWTService)
    if hasattr(service, "_initialized"):
        del service._initialized
    service.__init__()
    return service


def test_create_and_verify_access_token(jwt_service):
    token = jwt_service.create_access_token({"sub": "user-1", "role": "empleado"})
    payload = jwt_service.verify_token(token)

    assert payload["sub"] == "user-1"
    assert payload["role"] == "empleado"
    assert payload["type"] == "access"


def test_create_and_verify_refresh_token(jwt_service):
    token = jwt_service.create_refresh_token({"sub": "user-1"})
    payload = jwt_service.verify_token(token)

    assert payload["sub"] == "user-1"
    assert payload["type"] == "refresh"


def test_expired_token_raises(jwt_service):
    from datetime import timedelta

    token = jwt_service.create_access_token(
        {"sub": "user-1"}, expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(TokenExpiredError):
        jwt_service.verify_token(token)


def test_invalid_token_raises(jwt_service):
    with pytest.raises(InvalidTokenError):
        jwt_service.verify_token("not-a-valid-jwt")


def test_verify_token_rejects_wrong_secret(jwt_service):
    token = jwt_service.create_access_token({"sub": "user-1"})

    other = JWTService.__new__(JWTService)
    if hasattr(other, "_initialized"):
        del other._initialized
    other.__init__()
    other.secret_key = "a-different-secret"

    with pytest.raises(InvalidTokenError):
        other.verify_token(token)
