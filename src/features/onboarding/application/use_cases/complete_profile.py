"""
Caso de uso: completar el perfil del paso 5 (borrador funcional — el
esquema real del perfil todavía no está diseñado, así que se acepta un
payload básico y se guarda tal cual en `onboarding_progress.data`). Es el
último paso: no hay uno siguiente que desbloquear, pero se llama a
`unlock_next_step` igualmente por simetría — no encuentra ningún paso
`locked` con ese `step_order + 1` y no hace nada.
"""

from typing import Any

from ...domain.entities import OnboardingProgress
from ...domain.errors import (
    OnboardingStepNotFoundError,
    StepNotOperableError,
    WrongStepTypeError,
)
from ...domain.policy import ensure_step_allowed_for_role, ensure_step_operable
from ...domain.ports import IOnboardingRepository


class CompleteProfileUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self, *, user_id: str, role: str, step_id: str, data: dict[str, Any]
    ) -> OnboardingProgress:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "profile":
            raise WrongStepTypeError("Este paso no es de tipo perfil.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current)

        completed = await self._repository.mark_step_completed_if_operable(
            user_id, step_id, data=data
        )
        if completed is None:
            raise StepNotOperableError("Este paso ya no admite esta operación.")

        await self._repository.unlock_next_step(user_id, step.step_order)
        return completed
