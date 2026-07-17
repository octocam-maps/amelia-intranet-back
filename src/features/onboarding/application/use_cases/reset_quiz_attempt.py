"""
Caso de uso: `POST /onboarding/admin/steps/{step_id}/reset-quiz` — el
override que faltaba (ver `docs/` del reporte de la feature): un empleado
que suspende el cuestionario de un único intento quedaba bloqueado para
siempre en ese paso. El admin puede reabrirlo: borra el intento consumido y
reabre el progreso para que el empleado pueda reintentar.
"""

from ...domain.entities import OnboardingProgress
from ...domain.errors import (
    OnboardingProgressNotFoundError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.ports import IOnboardingRepository


class ResetQuizAttemptUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(self, *, step_id: str, user_id: str) -> OnboardingProgress:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "quiz":
            raise WrongStepTypeError(
                "Solo se puede reabrir un intento en un paso de tipo cuestionario."
            )

        progress = await self._repository.reset_quiz_attempt(user_id, step_id)
        if progress is None:
            raise OnboardingProgressNotFoundError(
                "Este usuario no tiene progreso inicializado en este paso."
            )
        return progress
