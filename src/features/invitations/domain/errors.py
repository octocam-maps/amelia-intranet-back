from src.shared.errors.base import NotFoundError, ValidationError


class InvitationNotFoundError(NotFoundError):
    """No existe una invitación con ese id."""


class InvitationNotCancellableError(ValidationError):
    """Solo se puede cancelar una invitación mientras siga `pending` Y la
    persona todavía no haya accedido (`users.status = 'invited'`). Cubre a
    la vez "ya fue cancelada", "ya fue aceptada" (RACE, mismo criterio que
    `AbsenceRequestAlreadyReviewedError`) y la persona ya activa/suspendida."""


class InvitationAlreadyCancelledError(ValidationError):
    """No se puede reenviar una invitación ya cancelada (`status = 'revoked'`)."""
