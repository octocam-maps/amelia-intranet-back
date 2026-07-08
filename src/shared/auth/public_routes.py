"""
Rutas públicas (no requieren Authorization header). Regla crítica del
proyecto: "ocultar ≠ proteger" — esta lista NO otorga acceso a nada, solo
evita exigir un token en los pocos endpoints que son intencionalmente
públicos. Todo lo demás pasa por `get_current_user` / `require_role`.
"""

import re

PUBLIC_ROUTES: set[str] = {
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}

PUBLIC_ROUTE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^/auth/login/?$"),
    re.compile(r"^/auth/refresh/?$"),
]


def is_public_route(path: str) -> bool:
    if path in PUBLIC_ROUTES:
        return True
    return any(pattern.match(path) for pattern in PUBLIC_ROUTE_PATTERNS)
