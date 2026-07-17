from src.shared.errors.base import (
    AlreadyExistsError,
    InsufficientPermissionsError,
    NotFoundError,
    ValidationError,
)


class AbsenceTypeNotFoundError(NotFoundError):
    """No existe un tipo de ausencia con ese id."""


class AbsenceTypeCodeAlreadyExistsError(AlreadyExistsError):
    """Ya existe un tipo de ausencia con ese `code` — viola `absence_types.code` UNIQUE."""


class AbsenceRequestNotFoundError(NotFoundError):
    """No existe una solicitud de ausencia con ese id."""


class InvalidDateRangeError(ValidationError):
    """`end_date` es anterior a `start_date`, o el rango no tiene ningún día laborable."""


class InsufficientBalanceError(ValidationError):
    """El saldo disponible del tipo de ausencia no cubre los días solicitados."""


class AbsenceRequestOverlapError(ValidationError):
    """Ya existe una solicitud `pending`/`approved` del mismo usuario que
    solapa con el rango de fechas solicitado.

    Granularidad (pendiente de confirmar con RRHH, ver README): el chequeo
    actual bloquea el solape contra CUALQUIER tipo de ausencia del usuario,
    no solo contra el mismo `absence_type_id` — no está confirmado si dos
    tipos distintos (p.ej. "vacaciones" y "asuntos propios") deberían poder
    coexistir el mismo día."""


class AbsenceRequestAlreadyReviewedError(ValidationError):
    """La solicitud ya fue aprobada/rechazada — no admite una segunda revisión."""


class AbsenceForbiddenError(InsufficientPermissionsError):
    """Un empleado intenta leer/actuar sobre la solicitud de otro usuario, o
    un no-admin intenta abrir la bandeja/aprobar (docs/permisos-roles.md § Ausencias)."""
