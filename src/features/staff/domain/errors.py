from src.shared.errors.base import AlreadyExistsError, NotFoundError, ValidationError


class StaffMemberNotFoundError(NotFoundError):
    """No existe una persona de la plantilla con ese id."""


class StaffEmailAlreadyExistsError(AlreadyExistsError):
    """Ya existe un usuario con ese email — viola `users.email` UNIQUE."""


class InvalidEntityCodeError(ValidationError):
    """El código de entidad no corresponde a `hub`/`lab`/`ops`."""


class InvalidRoleCodeError(ValidationError):
    """El código de rol no corresponde a `administrador`/`empleado`/`externo_invitado`."""
