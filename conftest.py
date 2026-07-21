"""
Fixture compartida por TODA la suite (pytest carga automáticamente el
`conftest.py` de la raíz para cualquier test bajo `src/`, sin que cada
archivo tenga que importarlo).

AUTHN-2 (pentest, severidad MEDIA): `get_current_user` ahora hace un SELECT
de `users.status` por request para cortar el acceso de inmediato si un
admin suspende a alguien (ver `src/shared/auth/dependencies.py`). Eso
introduce una dependencia real de Postgres en CUALQUIER endpoint
autenticado.

Los tests route-level (`TestClient(app)` + `dependency_overrides`,
repartidos en ~18 archivos `test_*_routes.py`) deliberadamente NO levantan
Postgres (ver README § Tests: "corren sin arrancar Postgres ni
credenciales reales de Google") — solo verifican JWT + RBAC con el rol
embebido en el token y casos de uso fakeados. Sin este fixture, esos tests
rompen con `RuntimeError: Database pool not initialized`, no con el 403/200
que en realidad quieren probar.

Este fixture es un doble mínimo (`fetchval` siempre devuelve "active") que
sustituye a `get_database_pool` SOLO dentro de `ensure_user_is_active` —
cualquier test que quiera probar explícitamente a un usuario suspendido
puede sobreescribir el mismo mock localmente con `monkeypatch` (mismo
patrón que `src/shared/auth/tests/test_dependencies.py`).
"""

import pytest


class _DefaultActiveStatusPool:
    async def fetchval(self, query, *args):
        return "active"


@pytest.fixture(autouse=True)
def _default_active_user_status(monkeypatch):
    monkeypatch.setattr(
        "src.shared.auth.dependencies.get_database_pool",
        lambda: _DefaultActiveStatusPool(),
    )
