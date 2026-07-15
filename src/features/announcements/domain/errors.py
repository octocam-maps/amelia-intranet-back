from src.shared.errors.base import NotFoundError, ValidationError


class AnnouncementNotFoundError(NotFoundError):
    """No existe un anuncio con ese id."""


class InvalidAudienceTargetError(ValidationError):
    """`audience='entity'` sin `entity_code` válido, o `audience='role'` sin
    `role_code` válido — el objetivo de la audiencia es obligatorio salvo
    que `audience='all'`."""
