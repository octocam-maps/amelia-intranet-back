from src.shared.errors.base import AlreadyExistsError, NotFoundError, ValidationError


class StaffMemberNotFoundError(NotFoundError):
    """No existe una persona de la plantilla con ese id."""


class StaffEmailAlreadyExistsError(AlreadyExistsError):
    """Ya existe un usuario con ese email — viola `users.email` UNIQUE."""


class InvalidEntityCodeError(ValidationError):
    """El código de entidad no corresponde a `hub`/`lab`/`ops`."""


class InvalidRoleCodeError(ValidationError):
    """El código de rol no existe en la tabla `roles` (fuente única — ver
    `GET /roles`, feature `roles`). Ya no es una lista fija en código: se
    resuelve dinámicamente vía `IStaffRepository.resolve_role_id`."""


# --- Baja definitiva (soft delete con anonimización) ---


class CannotDeleteYourselfError(ValidationError):
    """Un administrador intenta darse de baja a sí mismo.

    No es paternalismo: la baja revoca las sesiones, así que quien la ejecuta
    perdería el acceso a mitad de la operación y no podría deshacerla."""


class CannotDeleteLastAdminError(ValidationError):
    """La baja dejaría la intranet SIN ningún administrador activo.

    `docs/permisos-roles.md` define un único administrador, así que este caso
    no es hipotético: es el error de un clic. Sin nadie que administre, no hay
    forma de dar de alta a otro admin desde la propia aplicación."""
