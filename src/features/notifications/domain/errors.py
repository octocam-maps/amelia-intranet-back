from src.shared.errors.base import NotFoundError, ValidationError


class NotificationNotFoundError(NotFoundError):
    """No existe una notificación con ese id PARA ESE USUARIO. RGPD: no se
    distingue "no existe" de "es de otro usuario" — ambos casos devuelven
    404, así se evita filtrar si un id de otro usuario existe de verdad."""


class UnknownNotificationTypeError(ValidationError):
    """`type` no está en el catálogo cerrado `NOTIFICATION_TYPES`."""
