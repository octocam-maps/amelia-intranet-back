"""
Auditoría QA Fase 3: un id_token de Google mal verificado
(`GoogleOIDCVerificationError`) debe responder 401, no el 500 genérico que
recibía antes de que la excepción heredara de `BaseError`.
"""

import pytest

from src.shared.errors.handler import _status_for
from src.shared.google_oidc import GoogleOIDCVerificationError


def test_google_oidc_verification_error_maps_to_401():
    assert _status_for(GoogleOIDCVerificationError("bad token")) == 401


def test_unmapped_base_error_falls_back_to_500():
    from src.shared.errors.base import BaseError

    class _UnmappedError(BaseError):
        pass

    assert _status_for(_UnmappedError("boom")) == 500


@pytest.mark.asyncio
async def test_validation_error_with_a_value_error_serializes_instead_of_crashing():
    """Bug real, encontrado cazando el parte del técnico y presente en
    producción para TODOS los endpoints con `field_validator` propio.

    Cuando un validador de Pydantic v2 lanza `ValueError` (p. ej.
    `_require_offset` de `time_clock`), el error lleva la EXCEPCIÓN en
    `ctx["error"]`. `JSONResponse` la pasa por `json.dumps`, que no sabe
    serializar un objeto `ValueError` y revienta — el handler global convertía
    el fallo en un 500 "error del servidor" en vez del 422 con el motivo, para
    un dato mal formado que quien llama puede corregir.
    """
    import json

    from fastapi.exceptions import RequestValidationError

    from src.shared.errors.handler import validation_error_handler

    exc = RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "started_at"),
                "msg": "Value error, falta el offset",
                "input": "2026-08-05T08:00:00",
                "ctx": {"error": ValueError("La fecha/hora debe incluir el offset")},
            }
        ]
    )

    response = await validation_error_handler(None, exc)

    assert response.status_code == 422
    detail = json.loads(response.body)["detail"]
    # El motivo debe SOBREVIVIR a la serialización: reducirlo a `{}` dejaría al
    # cliente con un 422 que no dice qué está mal.
    assert detail[0]["ctx"]["error"] == "La fecha/hora debe incluir el offset"
    assert detail[0]["loc"] == ["body", "started_at"]
