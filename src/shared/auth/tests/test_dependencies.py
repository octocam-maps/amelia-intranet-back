"""
RBAC: `require_role` debe rechazar en el backend a cualquier rol no
autorizado, aunque el navbar del frontend nunca hubiera mostrado esa opción
("ocultar ≠ proteger" — docs/permisos-roles.md).

AUTHN-1: `get_current_user` debe rechazar un refresh token usado como Bearer
(confusión de tokens) — `verify_token` solo valida firma/exp, no el claim
`type`, así que la distinción access/refresh vive aquí. Se cubren los DOS
caminos de `get_current_user`: el fast-path cacheado por `AuthMiddleware`
(`request.state.current_user`) y la verificación directa del header
`Authorization`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from src.shared.auth.dependencies import get_current_user, require_role
from src.shared.auth.public_routes import is_public_route
from src.shared.errors.base import InsufficientPermissionsError, InvalidTokenError
from src.shared.jwt import get_jwt_service


@pytest.mark.asyncio
async def test_require_role_allows_matching_role():
    dependency = require_role("administrador")
    user = {"sub": "user-1", "role": "administrador"}

    result = await dependency(user=user)

    assert result == user


@pytest.mark.asyncio
async def test_require_role_rejects_non_matching_role():
    dependency = require_role("administrador")
    user = {"sub": "user-2", "role": "empleado"}

    with pytest.raises(InsufficientPermissionsError):
        await dependency(user=user)


@pytest.mark.asyncio
async def test_require_role_rejects_externo_from_admin_only_endpoint():
    dependency = require_role("administrador")
    user = {"sub": "user-3", "role": "externo_invitado"}

    with pytest.raises(InsufficientPermissionsError):
        await dependency(user=user)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/health", True),
        ("/", True),
        ("/auth/login", True),
        ("/auth/refresh", True),
        ("/auth/me", False),
        ("/auth/logout", False),
        ("/admin/plantilla", False),
    ],
)
def test_is_public_route(path, expected):
    assert is_public_route(path) is expected


class _FakeState:
    def __init__(self, current_user=None):
        self.current_user = current_user


class _FakeRequest:
    """Doble mínimo de `Request`: solo expone lo que `get_current_user` usa
    (`state.current_user` y `headers.get(...)`)."""

    def __init__(self, *, current_user=None, headers=None):
        self.state = _FakeState(current_user)
        self.headers = headers or {}


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class _FakePool:
    """Doble mínimo de `DatabasePool`: solo expone `fetchval`, que es lo
    único que usa `ensure_user_is_active` (AUTHN-2)."""

    def __init__(self, status: str = "active"):
        self._status = status

    async def fetchval(self, query, *args):
        return self._status


@pytest.fixture(autouse=True)
def _active_user_by_default(monkeypatch):
    """AUTHN-2 agrega un SELECT de estado en `get_current_user`. Todos los
    tests de este archivo asumen usuario activo salvo que sobreescriban
    `get_database_pool` explícitamente (evita romper los tests de AUTHN-1
    de arriba, que no conocen este chequeo)."""
    monkeypatch.setattr(
        "src.shared.auth.dependencies.get_database_pool",
        lambda: _FakePool("active"),
    )


@pytest.mark.asyncio
async def test_get_current_user_accepts_access_token_via_direct_verification():
    jwt_service = get_jwt_service()
    token = jwt_service.create_access_token({"sub": "user-1", "role": "empleado"})
    request = _FakeRequest()

    user = await get_current_user(request=request, credentials=_bearer(token))

    assert user["sub"] == "user-1"
    assert user["type"] == "access"


@pytest.mark.asyncio
async def test_get_current_user_rejects_refresh_token_via_direct_verification():
    """Un refresh token robado no debe servir como Bearer contra endpoints
    protegidos solo con `get_current_user` (p.ej. `/auth/me`, `/auth/logout`,
    `/auth/logout-all`)."""
    jwt_service = get_jwt_service()
    token = jwt_service.create_refresh_token({"sub": "user-1"})
    request = _FakeRequest()

    with pytest.raises(InvalidTokenError):
        await get_current_user(request=request, credentials=_bearer(token))


@pytest.mark.asyncio
async def test_get_current_user_accepts_access_token_from_middleware_cache():
    jwt_service = get_jwt_service()
    token = jwt_service.create_access_token({"sub": "user-1", "role": "empleado"})
    payload = jwt_service.verify_token(token)
    request = _FakeRequest(current_user=payload)

    user = await get_current_user(request=request, credentials=None)

    assert user["sub"] == "user-1"


@pytest.mark.asyncio
async def test_get_current_user_rejects_refresh_token_cached_by_middleware():
    """GOTCHA: `AuthMiddleware` cachea CUALQUIER token válido en
    `request.state.current_user`, incluido uno de tipo refresh. Si la
    validación de `type` solo viviera en el camino de verificación directa,
    este fast path seguiría dejando pasar un refresh token."""
    jwt_service = get_jwt_service()
    token = jwt_service.create_refresh_token({"sub": "user-1"})
    payload = jwt_service.verify_token(token)
    request = _FakeRequest(current_user=payload)

    with pytest.raises(InvalidTokenError):
        await get_current_user(request=request, credentials=None)


@pytest.mark.asyncio
async def test_get_current_user_rejects_suspended_user(monkeypatch):
    """AUTHN-2: corte inmediato. Si un admin suspende a un usuario
    (`users.status = 'suspended'`), su access token vigente (firma/exp/type
    todavía válidos) debe dejar de servir de inmediato, no recién cuando
    expire (hasta 15 min después)."""
    jwt_service = get_jwt_service()
    token = jwt_service.create_access_token({"sub": "user-1", "role": "empleado"})
    request = _FakeRequest()
    monkeypatch.setattr(
        "src.shared.auth.dependencies.get_database_pool",
        lambda: _FakePool("suspended"),
    )

    with pytest.raises(InvalidTokenError):
        await get_current_user(request=request, credentials=_bearer(token))


@pytest.mark.asyncio
async def test_get_current_user_rejects_suspended_user_cached_by_middleware(
    monkeypatch,
):
    """Mismo caso pero por el fast-path cacheado por `AuthMiddleware` — el
    chequeo de estado debe aplicar en AMBOS caminos, no solo en la
    verificación directa."""
    jwt_service = get_jwt_service()
    token = jwt_service.create_access_token({"sub": "user-1", "role": "empleado"})
    payload = jwt_service.verify_token(token)
    request = _FakeRequest(current_user=payload)
    monkeypatch.setattr(
        "src.shared.auth.dependencies.get_database_pool",
        lambda: _FakePool("suspended"),
    )

    with pytest.raises(InvalidTokenError):
        await get_current_user(request=request, credentials=None)


@pytest.mark.asyncio
async def test_get_current_user_accepts_active_user():
    """Caso feliz explícito: usuario `active` en BD sigue pasando."""
    jwt_service = get_jwt_service()
    token = jwt_service.create_access_token({"sub": "user-1", "role": "empleado"})
    request = _FakeRequest()

    user = await get_current_user(request=request, credentials=_bearer(token))

    assert user["sub"] == "user-1"


@pytest.mark.asyncio
async def test_get_current_user_rejects_user_with_no_matching_row(monkeypatch):
    """Defensivo: si el `sub` del token no resuelve a ninguna fila (usuario
    borrado), `fetchval` devuelve `None` -> se trata como no activo, no como
    un 500 ni un pase silencioso."""
    jwt_service = get_jwt_service()
    token = jwt_service.create_access_token({"sub": "ghost-user", "role": "empleado"})
    request = _FakeRequest()
    monkeypatch.setattr(
        "src.shared.auth.dependencies.get_database_pool",
        lambda: _FakePool(None),
    )

    with pytest.raises(InvalidTokenError):
        await get_current_user(request=request, credentials=_bearer(token))
