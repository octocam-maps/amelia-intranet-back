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
