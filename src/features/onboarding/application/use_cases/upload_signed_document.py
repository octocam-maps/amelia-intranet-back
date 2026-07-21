"""
Caso de uso: completar el paso 3 subiendo el PDF ya firmado FUERA de la
plataforma (sustituye a la firma nativa, `sign_document.py`, eliminado —
sdd/docs-firmados-upload-drive). El binario/categoría/MIME/tamaño/Drive los
resuelve `UploadDocumentUseCase` COMPLETO (feature `documents`), inyectado
aquí como servicio de aplicación (D1: reuso cruzado de un "Open Host
Service", mismo criterio que `documents` ya reutiliza
`PostgresStaffRepository` de `staff`) — este caso de uso NO duplica
folder-caching, persistencia de `employee_documents` ni la notificación.

Lo único propio de onboarding es el enlace `onboarding_document_uploads`
(D3): sin él, `employee_documents.category='signed'` no distingue "esto
satisfizo el paso 3 de ESTE usuario" de un `signed` suelto que un admin
subiera vía `POST /documents` por otro motivo.

`user_id` SIEMPRE llega del JWT (nunca de un campo del payload) — este caso
de uso ni siquiera declara un parámetro alternativo para el dueño del
documento, así que no hay canal para suplantar a otro usuario.
"""

from src.features.documents.application.use_cases.upload_document import (
    UploadDocumentUseCase,
)

from ...domain.entities import OnboardingDocumentUpload
from ...domain.errors import (
    OnboardingDocumentNotFoundError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.policy import ensure_step_allowed_for_role, ensure_step_operable
from ...domain.ports import IOnboardingRepository


class UploadSignedOnboardingDocumentUseCase:
    def __init__(
        self,
        repository: IOnboardingRepository,
        upload_document_use_case: UploadDocumentUseCase,
    ):
        self._repository = repository
        self._upload_document = upload_document_use_case

    async def execute(
        self,
        *,
        user_id: str,
        role: str,
        step_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> OnboardingDocumentUpload:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "signature":
            raise WrongStepTypeError("Este paso no es de tipo firma.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current)

        document = await self._repository.find_active_document("signature")
        if document is None:
            raise OnboardingDocumentNotFoundError(
                "Todavía no hay un documento de firma configurado."
            )

        # Delega TODA la validación (categoría/MIME/tamaño), Drive y
        # `employee_documents` en el use case compartido — si lanza
        # (MIME inválido, archivo demasiado grande), el paso NO se completa
        # y no se crea ningún enlace: mismo criterio "todo o nada por
        # intento" que ya tenía el flujo admin.
        uploaded = await self._upload_document.execute(
            user_id=user_id,
            uploaded_by=user_id,
            category="signed",
            title=document.title,
            period=None,
            filename=filename,
            content=content,
            mime_type=mime_type,
        )

        upload = await self._repository.create_document_upload(
            user_id=user_id,
            onboarding_document_id=document.id,
            employee_document_id=uploaded.id,
        )

        completed = await self._repository.mark_step_completed_if_operable(
            user_id, step_id, data={"employee_document_id": uploaded.id}
        )
        if completed is not None:
            await self._repository.unlock_next_step(user_id, step.step_order)

        return upload
