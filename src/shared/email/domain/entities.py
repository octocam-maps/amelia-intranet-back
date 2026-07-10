"""Entidad de dominio del envío de email transaccional. Sin dependencias de
framework/SQL — el resultado de `IEmailSender.send()` es lo que cada
adaptador (mock hoy, SendGrid/Mailgun/SES el día que se implemente) devuelve
para que `NotifyUseCase` decida cómo registrar el intento."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EmailResult:
    status: str  # 'sent' | 'failed' — mismo dominio que `email_log.status`
    provider_message_id: Optional[str]
    error_detail: Optional[str] = None
