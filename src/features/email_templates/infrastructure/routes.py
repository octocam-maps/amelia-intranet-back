"""
Router de `/email-templates`: los textos de los correos automáticos.

ADMIN_ONLY entero. No es solo que sea configuración: quien edita estas plantillas
escribe el texto que la intranet manda EN NOMBRE de la empresa a toda la
plantilla. Es la misma superficie de confianza que "Anuncios", no la de un ajuste
personal.
"""

from fastapi import APIRouter, Depends

from src.shared.auth.dependencies import require_role
from src.shared.auth.roles import ADMIN_ONLY

from ..application.use_cases.manage_email_templates import (
    ListEmailTemplatesUseCase,
    PreviewEmailTemplateUseCase,
    RestoreEmailTemplateUseCase,
    UpdateEmailTemplateUseCase,
)
from .dependencies import (
    get_list_email_templates_use_case,
    get_preview_email_template_use_case,
    get_restore_email_template_use_case,
    get_update_email_template_use_case,
)
from .mappers import template_to_dto, templates_to_dto
from .schemas import (
    EmailTemplateDTO,
    EmailTemplateListDTO,
    EmailTemplatePreviewDTO,
    PreviewEmailTemplateDTO,
    UpdateEmailTemplateDTO,
)


def create_email_templates_router() -> APIRouter:
    router = APIRouter(prefix="/email-templates", tags=["email-templates"])

    @router.get("", response_model=EmailTemplateListDTO)
    async def list_email_templates(
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: ListEmailTemplatesUseCase = Depends(
            get_list_email_templates_use_case
        ),
    ):
        """El catálogo completo, incluidas las restauradas al texto por defecto:
        son las que el admin tiene que ver para poder reactivarlas."""
        templates = await use_case.execute()
        return templates_to_dto(templates)

    @router.patch("/{template_key}", response_model=EmailTemplateDTO)
    async def update_email_template(
        template_key: str,
        dto: UpdateEmailTemplateDTO,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: UpdateEmailTemplateUseCase = Depends(
            get_update_email_template_use_case
        ),
    ):
        """Guarda el texto del admin y reactiva la plantilla: editar es querer
        usar lo editado.

        No hay POST: el catálogo es CERRADO (lo siembra la migración 041 con los
        tipos de correo que el código sabe enviar). Una fila nueva no haría
        aparecer un correo nuevo, así que permitir crearlas lo sugeriría en falso.
        """
        template = await use_case.execute(
            template_key,
            subject=dto.subject,
            body=dto.body,
            updated_by=current_user["sub"],
        )
        return template_to_dto(template)

    @router.post("/{template_key}/restore", response_model=EmailTemplateDTO)
    async def restore_email_template(
        template_key: str,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: RestoreEmailTemplateUseCase = Depends(
            get_restore_email_template_use_case
        ),
    ):
        """Vuelve al texto por defecto del código SIN borrar lo que el admin
        había escrito — puede reactivarlo editándolo de nuevo."""
        template = await use_case.execute(template_key, updated_by=current_user["sub"])
        return template_to_dto(template)

    @router.post("/{template_key}/preview", response_model=EmailTemplatePreviewDTO)
    async def preview_email_template(
        template_key: str,
        dto: PreviewEmailTemplateDTO,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: PreviewEmailTemplateUseCase = Depends(
            get_preview_email_template_use_case
        ),
    ):
        """Renderiza con datos de ejemplo, SIN guardar y SIN enviar.

        POST y no GET aunque no escriba nada: el borrador que se previsualiza va
        en el cuerpo, y un asunto o un HTML en la query string se toparían con el
        límite de longitud de URL y quedarían en los logs de acceso.
        """
        subject, html = await use_case.execute(
            template_key, subject=dto.subject, body=dto.body
        )
        return EmailTemplatePreviewDTO(subject=subject, html=html)

    return router
