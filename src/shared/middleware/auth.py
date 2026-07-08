"""
Middleware que verifica el JWT UNA vez por request y lo cachea en
`request.state.current_user` para que `get_current_user` (Depends) no lo
vuelva a verificar. Las rutas públicas (`is_public_route`) se saltan la
verificación por completo.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.shared.auth.public_routes import is_public_route
from src.shared.jwt import get_jwt_service
from src.shared.logger import get_logger

logger = get_logger("middleware.auth")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or is_public_route(request.url.path):
            return await call_next(request)

        request.state.current_user = None

        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            return await call_next(request)

        token = authorization.split(" ")[1]

        try:
            jwt_service = get_jwt_service()
            request.state.current_user = jwt_service.verify_token(token)
        except Exception as e:
            # Token inválido: no cortamos aquí, dejamos que get_current_user
            # devuelva 401 con el mensaje adecuado.
            logger.debug(
                "Token verification failed in middleware",
                path=request.url.path,
                error_type=type(e).__name__,
            )

        return await call_next(request)
