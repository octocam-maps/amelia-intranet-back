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

    Solo `subject` y `body`: el MARCO del correo (cabecera con logo, botón
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
    body: str
    is_active: bool
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    # Alcance del fan-out (migración 042). Solo significa algo en las plantillas
    # que avisan a VARIAS personas — hoy únicamente `staff_joined_team`. En las
    # demás el destinatario no se elige: es la persona a la que le pasó la cosa.
    #
    # `'none'` = no enviar ese aviso. Distinto de `is_active = False`, que es
    # "usa el texto por defecto": el admin tiene que poder apagar el aviso al
    # equipo sin dejar de mandar la bienvenida al recién llegado.
    audience: Optional[str] = None
    audience_entity_id: Optional[str] = None
