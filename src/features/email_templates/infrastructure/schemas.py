"""DTOs del feature `email_templates`."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EmailTemplateDTO(BaseModel):
    template_key: str
    label: str
    description: str
    subject: str
    body: str
    # `False` = está usando el texto por defecto del código. La pantalla lo pinta
    # como "Por defecto" frente a "Editada", que es la distinción que el admin
    # necesita para saber qué ha tocado.
    is_active: bool
    updated_by: Optional[str]
    updated_at: Optional[datetime]


class EmailTemplateListDTO(BaseModel):
    templates: list[EmailTemplateDTO]
    # Placeholders que el admin puede usar. Se manda desde el backend en vez de
    # duplicar la lista en el frontend: la lista blanca de verdad está en
    # `render_placeholders`, y una copia en el cliente se habría quedado atrás.
    available_placeholders: list[str]


class UpdateEmailTemplateDTO(BaseModel):
    subject: str = Field(..., min_length=1, max_length=300)
    body: str = Field(..., min_length=1)


class PreviewEmailTemplateDTO(BaseModel):
    """Texto EN BORRADOR a previsualizar. Ambos opcionales: sin ellos se
    previsualiza lo ya guardado."""

    subject: Optional[str] = None
    body: Optional[str] = None


class EmailTemplatePreviewDTO(BaseModel):
    subject: str
    # HTML COMPLETO con el marco (`_shell`): logo, botón y pie. Se manda entero y
    # no solo el cuerpo para que la previsualización muestre lo que va a recibir
    # el destinatario, no una aproximación.
    html: str
