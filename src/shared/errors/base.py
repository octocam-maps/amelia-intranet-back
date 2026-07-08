"""
Clases base de error de la aplicación.
Todos los errores de dominio heredan de estas clases.
"""

from typing import Optional


class BaseError(Exception):
    """Excepción base para todos los errores de la aplicación."""

    def __init__(self, message: str, code: Optional[str] = None):
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(self.message)


class NotFoundError(BaseError):
    """Recurso no encontrado."""


class AlreadyExistsError(BaseError):
    """Recurso ya existente (violación de unicidad)."""


class InvalidCredentialsError(BaseError):
    """Credenciales inválidas (id_token de Google no verificable, etc.)."""


class AuthenticationRequiredError(InvalidCredentialsError):
    """No se proporcionó ningún token."""


class TokenError(BaseError):
    """Base para errores relacionados con tokens."""


class TokenExpiredError(TokenError):
    """El token (access o refresh) ha expirado."""


class TokenNotFoundError(TokenError):
    """El token no existe o no es válido."""


class InvalidTokenError(TokenError):
    """El token está mal formado o su firma no es válida (no expirado)."""


class ValidationError(BaseError):
    """Fallo de validación de negocio."""


class InsufficientPermissionsError(BaseError):
    """El usuario autenticado no tiene el rol/permiso requerido."""
