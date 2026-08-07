"""
Exception handlers de FastAPI. Traducen errores de dominio (`BaseError`) y de
validación de Pydantic a respuestas HTTP consistentes ({"detail": ...}).
"""

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.shared.google_oidc import GoogleOIDCVerificationError

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
    # `GoogleOIDCVerificationError` ya hereda de `InvalidCredentialsError`
    # (401) — se deja explícita aquí porque un id_token de Google mal
    # verificado fue justo el caso real que caía en el 500 genérico antes
    # de la auditoría QA Fase 3 (ver comentario en `google_oidc/verifier.py`).
    GoogleOIDCVerificationError: 401,
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
    # `jsonable_encoder` y no `exc.errors()` en crudo: cuando un
    # `field_validator` de Pydantic v2 lanza `ValueError` (p. ej.
    # `_require_offset` en `time_clock/infrastructure/schemas.py`), el error
    # incluye la EXCEPCIÓN en `ctx["error"]`. `JSONResponse` la pasa por
    # `json.dumps`, que no sabe serializar un objeto `ValueError` y revienta:
    # el cliente recibía un 500 —"error del servidor"— en vez del 422 con el
    # motivo, para un dato mal formado que es culpa suya y tiene arreglo.
    #
    # `custom_encoder` convierte esas excepciones a su mensaje, que es lo
    # único que le sirve a quien llama; sin él, `jsonable_encoder` las
    # reduciría a `{}` y el motivo se perdería igual.
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors(), custom_encoder={Exception: str})},
    )
