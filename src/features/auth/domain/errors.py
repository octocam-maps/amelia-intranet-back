from src.shared.errors.base import InsufficientPermissionsError, InvalidCredentialsError


class NotInvitedError(InsufficientPermissionsError):
    """La cuenta de Google no corresponde a ningún usuario ni invitación pendiente.

    Hereda de `InsufficientPermissionsError` (-> HTTP 403) a propósito: no es
    un fallo de credenciales (Google SÍ verificó la identidad), es que esa
    identidad no tiene autorización de alta en la intranet.
    """


class UserSuspendedError(InsufficientPermissionsError):
    """El usuario existe pero está suspendido (status='suspended')."""


class EmailNotVerifiedError(InvalidCredentialsError):
    """El id_token de Google trae `email_verified=false` (auditoría QA Fase
    3): Google verificó la firma del token, pero NO garantiza que el titular
    controle esa dirección de email — defensa en profundidad, nunca dado de
    alta ni loggeado como sesión válida con un email no verificado."""
