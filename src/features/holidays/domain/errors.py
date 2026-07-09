from src.shared.errors.base import AlreadyExistsError, NotFoundError, ValidationError


class HolidayNotFoundError(NotFoundError):
    """No existe un festivo con ese id."""


class HolidayAlreadyExistsError(AlreadyExistsError):
    """Ya existe un festivo en esa fecha para esa entidad (o para todas) —
    viola `uq_holiday_day_entity`."""


class InvalidEntityCodeError(ValidationError):
    """El código de entidad no corresponde a `hub`/`lab`/`ops`."""
