from .domain.entities import EmailResult
from .domain.ports import IEmailSender
from .infrastructure.factory import get_email_sender

__all__ = ["EmailResult", "IEmailSender", "get_email_sender"]
