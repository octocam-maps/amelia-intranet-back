from src.shared.errors.base import InsufficientPermissionsError, NotFoundError, ValidationError


class TimeClockEntryNotFoundError(NotFoundError):
    """No existe un tramo de fichaje con ese id."""


class TimeClockOverlapError(ValidationError):
    """El tramo solicitado se solapa con otro tramo ya registrado ese día."""


class InvalidTimeRangeError(ValidationError):
    """`clock_out` no es posterior a `clock_in`, o el tramo cruza de día."""


class TimeClockForbiddenError(InsufficientPermissionsError):
    """Un empleado intenta leer/editar/borrar el fichaje de otro usuario.

    Solo el admin tiene la vista aumentada de toda la plantilla
    (docs/permisos-roles.md § Control horario).
    """


# --- Fichaje en vivo (modelo "ambos" — botón play/pausa/salida del dashboard) ---


class TimeClockAlreadyClockedInError(ValidationError):
    """Ya hay un tramo abierto para hoy — no se puede fichar entrada dos veces
    sin fichar salida antes."""


class TimeClockNoOpenEntryError(ValidationError):
    """No hay ningún tramo abierto hoy — no hay nada que pausar/cerrar."""


class TimeClockBreakAlreadyOpenError(ValidationError):
    """Ya hay una pausa abierta en el tramo actual."""


class TimeClockNoOpenBreakError(ValidationError):
    """No hay ninguna pausa abierta que reanudar."""
