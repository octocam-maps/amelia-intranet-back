"""
Caso de uso: `GET /onboarding/me` — pasos aplicables al rol del usuario, con
su progreso y el desbloqueo ya calculado. Si el usuario todavía no tiene
filas de progreso (primera visita), las inicializa: el primer paso (por
`step_order`) nace `available`, el resto `locked`.
"""

from ...domain.entities import OnboardingProgress, OnboardingStep
from ...domain.policy import steps_applicable_to_role
from ...domain.ports import IOnboardingRepository


class GetMyOnboardingUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self, *, user_id: str, role: str
    ) -> list[tuple[OnboardingStep, OnboardingProgress]]:
        all_steps = await self._repository.list_active_steps()
        applicable_steps = steps_applicable_to_role(all_steps, role)

        # Idempotente — se puede llamar en cada visita a la pantalla de
        # onboarding sin duplicar ni resetear filas ya existentes.
        await self._repository.ensure_progress_initialized(user_id, applicable_steps)

        progress_by_step_id = {
            p.step_id: p for p in await self._repository.list_progress_for_user(user_id)
        }

        return [
            (step, progress_by_step_id[step.id])
            for step in applicable_steps
            if step.id in progress_by_step_id
        ]
