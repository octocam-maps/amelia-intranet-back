"""
Caso de uso: confirmar la lectura del manual del paso 4. Menos exigente que
la firma (sin `signature_hash`) — el externo-invitado también hace este
paso, es uno de los dos que su onboarding parcial incluye.
"""

from typing import Optional

from ...domain.entities import DocumentAcknowledgement
from ...domain.errors import (
    OnboardingDocumentNotFoundError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.policy import ensure_step_allowed_for_role, ensure_step_operable
from ...domain.ports import IOnboardingRepository


class AcknowledgeManualUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

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

        return acknowledgement
