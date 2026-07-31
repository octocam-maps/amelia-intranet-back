from src.shared.email.domain.entities import EmailTemplate
from src.shared.email.infrastructure.sendgrid_email_sender import _ALLOWED_PLACEHOLDERS

from .schemas import EmailTemplateDTO, EmailTemplateListDTO


def template_to_dto(template: EmailTemplate) -> EmailTemplateDTO:
    return EmailTemplateDTO(
        template_key=template.template_key,
        label=template.label,
        description=template.description,
        subject=template.subject,
        body=template.body,
        is_active=template.is_active,
        updated_by=template.updated_by,
        updated_at=template.updated_at,
    )


def templates_to_dto(templates: list[EmailTemplate]) -> EmailTemplateListDTO:
    return EmailTemplateListDTO(
        templates=[template_to_dto(t) for t in templates],
        # Fuente única: la lista blanca real de `render_placeholders`. Duplicarla
        # en el frontend habría dejado la ayuda de la pantalla desincronizada del
        # comportamiento en el primer placeholder que se añadiera.
        available_placeholders=list(_ALLOWED_PLACEHOLDERS),
    )
