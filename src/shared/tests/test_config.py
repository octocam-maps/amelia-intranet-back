"""Guardia fail-fast de configuración segura (`Settings._enforce_secure_defaults`).

En dev/test los defaults cómodos valen; en prod/stage un default inseguro debe
abortar el arranque.
"""

import pytest

from src.shared.config import _INSECURE_JWT_SECRET_DEFAULT, _MIN_JWT_SECRET_LENGTH, Settings

_STRONG_SECRET = "x" * _MIN_JWT_SECRET_LENGTH


def test_dev_tolerates_default_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    Settings()  # no debe lanzar


@pytest.mark.parametrize("env", ["prod", "stage"])
def test_protected_env_rejects_default_jwt_secret(monkeypatch, env):
    monkeypatch.setenv("ENVIRONMENT", env)
    monkeypatch.setenv("JWT_SECRET_KEY", _INSECURE_JWT_SECRET_DEFAULT)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        Settings()


def test_protected_env_rejects_short_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET_KEY", "corto")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        Settings()


def test_protected_env_accepts_strong_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET_KEY", _STRONG_SECRET)
    Settings()  # no debe lanzar
