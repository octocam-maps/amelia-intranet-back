from src.shared.errors.base import InsufficientPermissionsError, NotFoundError, ValidationError


class AbsenceTypeNotFoundError(NotFoundError):
    """No existe un tipo de ausencia con ese id."""


class AbsenceRequestNotFoundError(NotFoundError):
    """No existe una solicitud de ausencia con ese id."""


class InvalidDateRangeError(ValidationError):
    """`end_date` es anterior a `start_date`, o el rango no tiene ningún día laborable."""


class InsufficientBalanceError(ValidationError):
    """El saldo disponible del tipo de ausencia no cubre los días solicitados."""


class AbsenceRequestAlreadyReviewedError(ValidationError):
    """La solicitud ya fue aprobada/rechazada — no admite una segunda revisión."""


class AbsenceForbiddenError(InsufficientPermissionsError):
    """Un empleado intenta leer/actuar sobre la solicitud de otro usuario, o
    un no-admin intenta abrir la bandeja/aprobar (docs/permisos-roles.md § Ausencias)."""
