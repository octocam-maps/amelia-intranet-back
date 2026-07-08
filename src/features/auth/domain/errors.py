from src.shared.errors.base import InsufficientPermissionsError


class NotInvitedError(InsufficientPermissionsError):
    """La cuenta de Google no corresponde a ningún usuario ni invitación pendiente.

    Hereda de `InsufficientPermissionsError` (-> HTTP 403) a propósito: no es
    un fallo de credenciales (Google SÍ verificó la identidad), es que esa
    identidad no tiene autorización de alta en la intranet.
    """


class UserSuspendedError(InsufficientPermissionsError):
    """El usuario existe pero está suspendido (status='suspended')."""
