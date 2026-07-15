from src.shared.errors.base import NotFoundError


class MailboxMessageNotFoundError(NotFoundError):
    """No existe un mensaje del buzón con ese id o `reference_code`."""
