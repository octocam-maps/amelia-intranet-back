from src.shared.errors.base import NotFoundError


class ProfileNotFoundError(NotFoundError):
    """No existe un usuario con el id del token (usuario borrado/inexistente)."""
