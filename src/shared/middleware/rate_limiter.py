"""
Rate limiting (slowapi) para los endpoints públicos de auth
(`/auth/login`, `/auth/refresh`). Se aplica vía `@limiter.limit(...)`.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _resolve_client_key(request: Request) -> str:
    state_ip = getattr(request.state, "client_ip", None) if hasattr(request, "state") else None
    if state_ip:
        return state_ip
    return get_remote_address(request)


limiter = Limiter(key_func=_resolve_client_key)

__all__ = ["limiter"]
