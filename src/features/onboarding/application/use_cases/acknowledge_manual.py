"""
Caso de uso: confirmar la lectura de los manuales. Menos exigente que la
firma (sin `signature_hash`) — el externo-invitado también hace este paso, es
uno de los dos que su onboarding parcial incluye.

Tras la reordenación de v1.1 (`033_onboarding_steps_reorder_v11.sql`) este
paso es el 3 (antes el 4) y actúa de PUERTA: hasta que no se confirma la
lectura, el trabajador no llega al perfil ni a la documentación que tiene que
descargar, firmar y volver a subir. Es también el ÚLTIMO paso del
externo-invitado (su onboarding parcial es vídeo + manual), y por eso aquí
también se comprueba si el onboarding queda cerrado.
"""

from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import DocumentAcknowledgement
from ...domain.errors import (
    OnboardingDocumentNotFoundError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.policy import ensure_step_allowed_for_role, ensure_step_operable
from ...domain.ports import IOnboardingRepository
from .notify_onboarding_completed import NotifyOnboardingCompletedUseCase


class AcknowledgeManualUseCase:
    def __init__(
        self, repository: IOnboardingRepository, notify: Optional[NotifyUseCase] = None
    ):
        self._repository = repository
        self._notify_completion = (
            NotifyOnboardingCompletedUseCase(repository, notify)
            if notify is not None
            else None
        )

    async def execute(
        self, *, user_id: str, role: str, step_id: str, ip_address: Optional[str]
    ) -> DocumentAcknowledgement:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "manual":
            raise WrongStepTypeError("Este paso no es de tipo manual.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current)

        document = await self._repository.find_active_document("manual")
        if document is None:
            raise OnboardingDocumentNotFoundError(
                "Todavía no hay un manual configurado."
            )

        acknowledgement = await self._repository.create_acknowledgement(
            user_id=user_id, document_id=document.id, ip_address=ip_address
        )

        completed = await self._repository.mark_step_completed_if_operable(
            user_id, step_id, data={"document_id": document.id}
        )
        if completed is not None:
            await self._repository.unlock_next_step(user_id, step.step_order)

            # Cierra el onboarding del externo-invitado (vídeo + manual). Para
            # empleado/administrador/socio no notifica nada: les quedan el
            # perfil y la documentación, y `is_onboarding_complete` lo ve.
            if self._notify_completion is not None:
                await self._notify_completion.execute(user_id=user_id, role=role)

        return acknowledgement
