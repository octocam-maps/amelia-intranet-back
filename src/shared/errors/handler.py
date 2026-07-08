"""
Exception handlers de FastAPI. Traducen errores de dominio (`BaseError`) y de
validación de Pydantic a respuestas HTTP consistentes ({"detail": ...}).
"""

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .base import (
    AlreadyExistsError,
    AuthenticationRequiredError,
    BaseError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    InvalidTokenError,
    NotFoundError,
    TokenExpiredError,
    TokenNotFoundError,
    ValidationError,
)

_STATUS_BY_ERROR = {
    NotFoundError: 404,
    AlreadyExistsError: 409,
    ValidationError: 422,
    AuthenticationRequiredError: 401,
    InvalidCredentialsError: 401,
    InvalidTokenError: 401,
    TokenExpiredError: 401,
    TokenNotFoundError: 401,
    InsufficientPermissionsError: 403,
}


def _status_for(error: BaseError) -> int:
    for error_type, status_code in _STATUS_BY_ERROR.items():
        if isinstance(error, error_type):
            return status_code
    return 500


async def error_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, BaseError):
        status_code = _status_for(exc)
        return JSONResponse(
            status_code=status_code,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )
    # Error no controlado: no exponer detalles internos.
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "InternalServerError", "message": "Internal server error"}},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
