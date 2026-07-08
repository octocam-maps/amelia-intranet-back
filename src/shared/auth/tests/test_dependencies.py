"""
RBAC: `require_role` debe rechazar en el backend a cualquier rol no
autorizado, aunque el navbar del frontend nunca hubiera mostrado esa opción
("ocultar ≠ proteger" — docs/permisos-roles.md).
"""

import pytest

from src.shared.auth.dependencies import require_role
from src.shared.auth.public_routes import is_public_route
from src.shared.errors.base import InsufficientPermissionsError


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
