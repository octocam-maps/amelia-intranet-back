"""CORS y cabeceras de seguridad HTTP."""

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.shared.config import get_settings


def setup_cors(app) -> None:
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras de seguridad estándar en toda respuesta (excepto docs)."""

    EXCLUDED_PATHS = ["/docs", "/redoc", "/openapi.json"]

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    def _is_excluded(self, path: str) -> bool:
        return any(path.startswith(p) for p in self.EXCLUDED_PATHS)

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if self._is_excluded(request.url.path):
            return response

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
