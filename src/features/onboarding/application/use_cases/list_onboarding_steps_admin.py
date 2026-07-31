"""
Caso de uso: `GET /onboarding/admin/steps` — catálogo COMPLETO (activos e
inactivos) sin enmascarar. A diferencia de `GetMyOnboardingUseCase`, el
admin SÍ ve la respuesta correcta del quiz (`config.questions[].correct`)
porque es quien la edita — el enmascarado del mapper de `/onboarding/me`
no aplica aquí.

Desde el 2026-07-31 devuelve además los DOCUMENTOS de cada paso, para que el admin
pueda PREVISUALIZAR el paso tal como lo verá el trabajador (petición: "permite que
el administrador pueda ver los pasos del onboarding"). Sin ellos, la
previsualización del paso 3 mostraría una lista de manuales vacía y la del paso 5,
una plantilla inexistente.
"""

from ...domain.entities import OnboardingDocument, OnboardingStep
from ...domain.ports import IOnboardingRepository

# Los tipos de paso que llevan documento asociado. Los demás (vídeo, quiz, perfil)
# se describen enteros con su `config`.
_DOCUMENT_STEP_TYPES = ("manual", "signature")


class ListOnboardingStepsForAdminUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self,
    ) -> list[tuple[OnboardingStep, list[OnboardingDocument]]]:
        steps = await self._repository.list_all_steps()

        # Una consulta por TIPO presente (2 como máximo), no una por paso.
        documents_by_kind: dict[str, list[OnboardingDocument]] = {}
        for kind in _DOCUMENT_STEP_TYPES:
            if any(step.type == kind for step in steps):
                documents_by_kind[kind] = await self._repository.find_active_documents(
                    kind
                )

        return [(step, documents_by_kind.get(step.type, [])) for step in steps]
