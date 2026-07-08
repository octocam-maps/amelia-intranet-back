from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.shared.utils.client_ip import get_client_ip


class ClientIPMiddleware(BaseHTTPMiddleware):
    """Resuelve la IP real del cliente antes de que llegue a cualquier handler."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request.state.client_ip = get_client_ip(request)
        return await call_next(request)
