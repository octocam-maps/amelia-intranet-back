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
    monkeypatch.delenv("REFRESH_TOKEN_COOKIE_SECURE", raising=False)
    Settings()  # no debe lanzar


def test_protected_env_defaults_cookie_secure_true(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.delenv("REFRESH_TOKEN_COOKIE_SECURE", raising=False)
    assert Settings().refresh_token_cookie_secure is True


def test_protected_env_rejects_explicit_insecure_cookie(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("REFRESH_TOKEN_COOKIE_SECURE", "false")
    with pytest.raises(RuntimeError, match="REFRESH_TOKEN_COOKIE_SECURE"):
        Settings()


def test_dev_keeps_cookie_insecure_default(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("REFRESH_TOKEN_COOKIE_SECURE", raising=False)
    assert Settings().refresh_token_cookie_secure is False
