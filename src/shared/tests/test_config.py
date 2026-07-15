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


# --- SWAGGER_ENABLED: solo dev/test por defecto (bug real, auditoría QA) ---


@pytest.mark.parametrize("env", ["dev", "test"])
def test_dev_and_test_enable_swagger_by_default(monkeypatch, env):
    monkeypatch.setenv("ENVIRONMENT", env)
    monkeypatch.delenv("SWAGGER_ENABLED", raising=False)
    assert Settings().swagger_enabled is True


@pytest.mark.parametrize("env", ["prod", "stage"])
def test_protected_env_disables_swagger_by_default(monkeypatch, env):
    monkeypatch.setenv("ENVIRONMENT", env)
    monkeypatch.setenv("JWT_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("REFRESH_TOKEN_COOKIE_SECURE", "true")
    monkeypatch.delenv("SWAGGER_ENABLED", raising=False)
    assert Settings().swagger_enabled is False


def test_protected_env_allows_explicit_swagger_override(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("REFRESH_TOKEN_COOKIE_SECURE", "true")
    monkeypatch.setenv("SWAGGER_ENABLED", "true")
    assert Settings().swagger_enabled is True


# --- CORS wildcard + credenciales: fail-fast en prod/stage ---


def test_protected_env_rejects_cors_wildcard(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        Settings()


def test_protected_env_accepts_explicit_cors_origins(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("REFRESH_TOKEN_COOKIE_SECURE", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://intranet.ameliahub.com")
    Settings()  # no debe lanzar


def test_dev_tolerates_cors_wildcard(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    Settings()  # no debe lanzar
