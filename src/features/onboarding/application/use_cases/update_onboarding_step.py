"""
Caso de uso: `PATCH /onboarding/admin/steps/{step_id}` — edición parcial de
un paso del catálogo. El merge de "qué campo se queda igual" pasa AQUÍ (no
en el repositorio): así el `UPDATE` de infraestructura recibe siempre los
tres valores finales y no hay que resolver la ambigüedad de un `config`
JSONB opcional contra `COALESCE` (un `None` de Python que representara "no
tocar" es indistinguible en JSON de un `config` que de verdad valga `null`).
"""

from typing import Any, Optional

from ...domain.entities import OnboardingStep
from ...domain.errors import OnboardingStepNotFoundError
from ...domain.policy import validate_step_config
from ...domain.ports import IOnboardingRepository


class UpdateOnboardingStepUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        step_id: str,
        title: Optional[str] = None,
        is_active: Optional[bool] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> OnboardingStep:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")

        final_title = title if title is not None else step.title
        final_is_active = is_active if is_active is not None else step.is_active
        final_config = config if config is not None else step.config

        if config is not None:
            validate_step_config(step.type, final_config)

        updated = await self._repository.update_step(
            step_id,
            title=final_title,
            is_active=final_is_active,
            config=final_config,
        )
        if updated is None:
            # Carrera con un borrado del paso — no hay DELETE hoy, pero no
            # asumimos que nunca lo habrá.
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        return updated
