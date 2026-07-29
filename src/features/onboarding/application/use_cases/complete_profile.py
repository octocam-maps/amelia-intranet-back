"""
Caso de uso: completar el perfil del paso 5 ("Completar perfil", RF §3.5).
Los 6 campos de texto + fecha de nacimiento son obligatorios (`company_phone`
es el único opcional); el backend rechaza el payload si cualquiera de ellos
viene vacío, de solo espacios o ausente — y si el `department_id` no
corresponde a un departamento real. El paso NO se marca `completed` si esta
validación falla: "ocultar ≠ proteger", el bloqueo real es este chequeo, no
el formulario del frontend. Los datos ya no se guardan en el JSONB de
`onboarding_progress.data` (borrador anterior) — se persisten en
`users`/`user_profiles`, su ubicación real.

El perfil YA NO es el último paso. Lo era (`step_order=5`, seed
`020_onboarding_steps_seed.sql`) y este caso de uso disparaba directamente
`onboarding_completed` por eso; la reordenación de v1.1
(`033_onboarding_steps_reorder_v11.sql`) lo movió al 4 y puso la subida de
documentación firmada en el 5. El aviso a RRHH se delega ahora en
`NotifyOnboardingCompletedUseCase`, que comprueba el ESTADO real de todos
los pasos aplicables al rol en vez de asumir que este es el que cierra el
flujo — si aún falta la documentación, no notifica nada.

El externo-invitado nunca alcanza este paso (`ensure_step_allowed_for_role`
lo rechaza porque su onboarding parcial no incluye `type='profile'`).
"""

from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import OnboardingProgress, ProfileCompletionData
from ...domain.errors import (
    InvalidDepartmentError,
    OnboardingStepNotFoundError,
    OnboardingUserNotFoundError,
    StepNotOperableError,
    WrongStepTypeError,
)
from ...domain.policy import (
    ensure_profile_data_complete,
    ensure_step_allowed_for_role,
    ensure_step_operable,
)
from ...domain.ports import IOnboardingRepository
from .notify_onboarding_completed import NotifyOnboardingCompletedUseCase


class CompleteProfileUseCase:
    def __init__(self, repository: IOnboardingRepository, notify: Optional[NotifyUseCase] = None):
        self._repository = repository
        # Opcional para no romper los tests existentes que no lo pasan —
        # mismo criterio que `CreateAbsenceRequestUseCase`/
        # `ReviewAbsenceRequestUseCase`.
        self._notify = notify
        # Se construye a partir de lo YA inyectado (repositorio + notify), así
        # que el cableado de `infrastructure/dependencies.py` no cambia al
        # mover el disparador de finalización fuera de este caso de uso.
        self._notify_completion = (
            NotifyOnboardingCompletedUseCase(repository, notify)
            if notify is not None
            else None
        )

    async def execute(
        self, *, user_id: str, role: str, step_id: str, profile: ProfileCompletionData
    ) -> OnboardingProgress:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "profile":
            raise WrongStepTypeError("Este paso no es de tipo perfil.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current)

        # Segunda barrera anti-vacío (la primera es el DTO de FastAPI) —
        # regla no negociable del requerimiento §7.
        ensure_profile_data_complete(profile)

        if not await self._repository.department_exists(profile.department_id):
            raise InvalidDepartmentError("El departamento indicado no existe.")

        saved = await self._repository.save_profile_completion(user_id, profile)
        if not saved:
            raise OnboardingUserNotFoundError("No se encontró el usuario del token.")

        completed = await self._repository.mark_step_completed_if_operable(
            user_id, step_id, data={}
        )
        if completed is None:
            raise StepNotOperableError("Este paso ya no admite esta operación.")

        await self._repository.unlock_next_step(user_id, step.step_order)

        # Solo notifica si con este paso el onboarding queda REALMENTE
        # terminado — completar el perfil ya no implica haber acabado.
        if self._notify_completion is not None:
            await self._notify_completion.execute(user_id=user_id, role=role)

        return completed
