"""Entidad de dominio del envío de email transaccional. Sin dependencias de
framework/SQL — el resultado de `IEmailSender.send()` es lo que cada
adaptador (mock hoy, SendGrid/Mailgun/SES el día que se implemente) devuelve
para que `NotifyUseCase` decida cómo registrar el intento."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class EmailResult:
    status: str  # 'sent' | 'failed' — mismo dominio que `email_log.status`
    provider_message_id: Optional[str]
    error_detail: Optional[str] = None


@dataclass(frozen=True)
class EmailTemplate:
    """Plantilla editable por el administrador (`email_templates`, migración 041).

    Solo `subject` y `body_html`: el MARCO del correo (cabecera con logo, botón
    de CTA, pie) sigue en código y no se expone. Si el admin pudiera editar el
    HTML completo, un guardado mal hecho saldría sin logo o con el layout roto
    para toda la plantilla, y nadie lo vería hasta que llegara a las bandejas.

    `is_active = False` significa "usa el texto por defecto del código", no
    "no mandes el correo": es el botón «Restaurar» de la pantalla de
    administración, y conserva lo que el admin había escrito por si quiere
    volver.
    """

    template_key: str
    label: str
    description: str
    subject: str
    body_html: str
    is_active: bool
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None
