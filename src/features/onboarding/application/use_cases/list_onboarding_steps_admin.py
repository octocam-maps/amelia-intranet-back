"""
Caso de uso: `GET /onboarding/admin/steps` — catálogo COMPLETO (activos e
inactivos) sin enmascarar. A diferencia de `GetMyOnboardingUseCase`, el
admin SÍ ve la respuesta correcta del quiz (`config.questions[].correct`)
porque es quien la edita — el enmascarado del mapper de `/onboarding/me`
no aplica aquí.
"""

from ...domain.entities import OnboardingStep
from ...domain.ports import IOnboardingRepository


class ListOnboardingStepsForAdminUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(self) -> list[OnboardingStep]:
        return await self._repository.list_all_steps()
