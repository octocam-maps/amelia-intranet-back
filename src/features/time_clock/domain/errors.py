from src.shared.errors.base import InsufficientPermissionsError, NotFoundError, ValidationError


class TimeClockEntryNotFoundError(NotFoundError):
    """No existe un tramo de fichaje con ese id."""


class TimeClockOverlapError(ValidationError):
    """El tramo solicitado se solapa con otro tramo ya registrado ese día."""


class InvalidTimeRangeError(ValidationError):
    """`clock_out` no es posterior a `clock_in`, o el tramo cruza de día."""


class ManualEntryOutOfWindowError(ValidationError):
    """`work_date` del alta manual cae fuera de la ventana permitida — en el
    futuro, o más allá de `Settings.time_clock_manual_entry_max_past_days`
    días atrás (LOGIC-2, pentest ético, severidad ALTA: sin este límite,
    cualquier interno podía fichar un tramo para hace 3 años o para el año
    que viene, ya que `work_date`/`clock_in`/`clock_out` del alta manual
    llegan arbitrarios en el body). Solo aplica al ALTA MANUAL
    (`CreateTimeClockEntryUseCase`) — el fichaje en vivo (`clock_in`/
    `clock_out`) usa siempre la hora del servidor y no recibe fecha del
    cliente, así que no puede estar fuera de ventana."""


class TimeClockForbiddenError(InsufficientPermissionsError):
    """Un empleado intenta leer/editar/borrar el fichaje de otro usuario.

    Solo el admin tiene la vista aumentada de toda la plantilla
    (docs/permisos-roles.md § Control horario).
    """


class TimeClockNoteBodyRequiredError(ValidationError):
    """La incidencia/comentario no puede estar vacía (B-2b)."""


# --- Alta de fichaje en lote por rango de días (RF-A3) ---


class TimeClockBatchDateRangeInvertedError(ValidationError):
    """`date_from` es posterior a `date_to` en el alta en lote — rechazo
    estructural, previo a clasificar ningún día."""


class TimeClockBatchRangeTooLongError(ValidationError):
    """El rango del lote supera el tope de días permitido por alta —
    rechazo estructural, previo a clasificar ningún día."""


class TimeClockBatchFutureDateError(ValidationError):
    """LOGIC-2 (pentest ético, severidad ALTA): al menos un día laborable
    del lote, tras aplicar las exclusiones de calendario (fin de semana,
    festivo, ausencia aprobada), sigue cayendo en el futuro (Europe/Madrid).
    Rechaza TODO el lote sin escribir ningún tramo — omitir en silencio ese
    día daría una falsa sensación de "lote aplicado" ocultando un intento
    de violar la ventana temporal del alta manual (mismo fix que protege
    `CreateTimeClockEntryUseCase._validate_window`, aquí a nivel de lote)."""


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


# --- Parte diario del técnico (requerimiento v1.2 §M1) ---


class TechnicianDailyLogNotFoundError(NotFoundError):
    """No existe un parte diario con ese id."""


class DuplicateDailyLogError(ValidationError):
    """Ya hay un parte para ese técnico y día. «Se creará un registro diario»:
    uno, no varios tramos como en el fichaje estándar. Se edita el que hay."""


class InvalidBreakError(ValidationError):
    """La pausa declarada es incoherente: minutos informados habiendo marcado
    que no hubo pausa, `had_break` sin minutos, o una pausa que se come la
    jornada entera."""


class ProjectNotFoundError(NotFoundError):
    """El proyecto no existe o está inactivo."""


class InsufficientCompensationBalanceError(ValidationError):
    """El descanso compensatorio solicitado supera el saldo de horas extra
    devengado y no disfrutado."""
