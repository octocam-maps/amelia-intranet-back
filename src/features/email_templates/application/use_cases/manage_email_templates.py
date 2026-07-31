"""
Casos de uso de la pantalla de plantillas de email (migración 041).

Son tres verbos sobre un catálogo CERRADO: listar, editar y restaurar. No hay
"crear" ni "borrar" a propósito — las plantillas existentes son los ~15 tipos de
correo que el código sabe enviar, y una fila nueva en la tabla no haría que
apareciera un correo nuevo. Dejar crear plantillas sugeriría que sí.
"""

from typing import Any, Optional

from src.shared.email.domain.entities import EmailTemplate
from src.shared.email.infrastructure.sendgrid_email_sender import render_email

from ...domain.errors import EmailTemplateNotFoundError, InvalidEmailTemplateError
from ...domain.ports import IEmailTemplateRepository

# Datos de ejemplo para la previsualización. Fijos y reconocibles como ficticios:
# usar datos de una persona real de la plantilla para previsualizar un correo
# expondría sus datos en una pantalla que no es su ficha.
_PREVIEW_CONTEXT: dict[str, Any] = {
    "full_name": "Ana Ejemplo",
    "entity_name": "Amelia Hub",
    "job_title": "Project Manager",
    "title": "Título de ejemplo de la notificación",
    "body": "Este es el texto que escribe la intranet para este aviso.",
    "url": "/",
}


class ListEmailTemplatesUseCase:
    def __init__(self, repository: IEmailTemplateRepository):
        self._repository = repository

    async def execute(self) -> list[EmailTemplate]:
        return await self._repository.list_templates()


class UpdateEmailTemplateUseCase:
    def __init__(self, repository: IEmailTemplateRepository):
        self._repository = repository

    async def execute(
        self,
        template_key: str,
        *,
        subject: str,
        body_html: str,
        updated_by: Optional[str] = None,
    ) -> EmailTemplate:
        # Un asunto vacío deja el correo con la línea en blanco en la bandeja de
        # entrada, y un cuerpo vacío lo deja sin mensaje: las dos cosas pasan el
        # tipo (`str`) pero no son un correo. Se rechazan aquí y no solo en el
        # `min_length` del DTO porque el caso de uso es lo que se puede testear.
        if not subject.strip():
            raise InvalidEmailTemplateError("El asunto no puede estar vacío.")
        if not body_html.strip():
            raise InvalidEmailTemplateError(
                "El cuerpo del correo no puede estar vacío."
            )

        updated = await self._repository.update_template(
            template_key,
            subject=subject.strip(),
            body_html=body_html.strip(),
            updated_by=updated_by,
        )
        if updated is None:
            raise EmailTemplateNotFoundError("Esa plantilla de correo no existe.")
        return updated


class RestoreEmailTemplateUseCase:
    """«Restaurar el texto por defecto»: desactiva la personalización sin
    borrarla, así el admin puede volver a su versión."""

    def __init__(self, repository: IEmailTemplateRepository):
        self._repository = repository

    async def execute(
        self, template_key: str, *, updated_by: Optional[str] = None
    ) -> EmailTemplate:
        restored = await self._repository.deactivate_template(
            template_key, updated_by=updated_by
        )
        if restored is None:
            raise EmailTemplateNotFoundError("Esa plantilla de correo no existe.")
        return restored


class PreviewEmailTemplateUseCase:
    """Renderiza un asunto y un cuerpo con datos de ejemplo, SIN guardar y SIN
    enviar.

    Recibe el texto que el admin tiene en pantalla (no el guardado) para que pueda
    ver el resultado antes de decidir si lo guarda. Es lo que evita que descubra
    una errata cuando el correo ya salió a toda la plantilla.
    """

    def __init__(self, repository: IEmailTemplateRepository, *, frontend_url: str):
        self._repository = repository
        self._frontend_url = frontend_url

    async def execute(
        self,
        template_key: str,
        *,
        subject: Optional[str] = None,
        body_html: Optional[str] = None,
    ) -> tuple[str, str]:
        existing = await self._repository.find_by_key(template_key)
        if existing is None:
            raise EmailTemplateNotFoundError("Esa plantilla de correo no existe.")

        # Sin texto en la petición se previsualiza lo GUARDADO; con texto, el
        # borrador que el admin está escribiendo.
        draft = EmailTemplate(
            template_key=existing.template_key,
            label=existing.label,
            description=existing.description,
            subject=subject if subject is not None else existing.subject,
            body_html=body_html if body_html is not None else existing.body_html,
            # Forzado a `True`: se previsualiza el texto personalizado incluso si
            # la plantilla está restaurada al de fábrica — si no, el admin
            # escribiría un borrador y la previsualización le devolvería el texto
            # de fábrica sin explicar por qué.
            is_active=True,
        )
        return render_email(
            template_key,
            _PREVIEW_CONTEXT,
            frontend_url=self._frontend_url,
            override=draft,
        )
