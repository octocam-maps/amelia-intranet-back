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

Este es también el paso 5, EL ÚLTIMO de los 5 (`step_order=5`, seed
`020_onboarding_steps_seed.sql`) — y el externo-invitado nunca lo alcanza
(`ensure_step_allowed_for_role` lo rechaza porque su onboarding parcial no
incluye `type='profile'`). Completarlo con éxito es, por tanto, el momento
exacto en que un trabajador de onboarding COMPLETO (empleado/administrador/
socio) termina los 5 pasos: dispara `onboarding_completed` a RRHH (RF §2.7)
con nombre, fecha/hora de finalización, nota del cuestionario y confirmación
de documentos firmados. Idempotente por construcción: `mark_step_completed_if_
operable` solo puede tener éxito UNA vez por usuario/paso (una segunda
llamada ya no encuentra el paso en `available`/`in_progress` y
`ensure_step_operable` la rechaza más arriba con `StepNotOperableError`
antes de volver a llegar aquí) — no hace falta un chequeo de idempotencia
aparte, el propio estado del paso lo garantiza.
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


class CompleteProfileUseCase:
    def __init__(self, repository: IOnboardingRepository, notify: Optional[NotifyUseCase] = None):
        self._repository = repository
        # Opcional para no romper los tests existentes que no lo pasan —
        # mismo criterio que `CreateAbsenceRequestUseCase`/
        # `ReviewAbsenceRequestUseCase`.
        self._notify = notify

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

        if self._notify is not None:
            await self._notify_admins_of_completion(
                user_id=user_id, profile=profile, completed=completed
            )

        return completed

    async def _notify_admins_of_completion(
        self, *, user_id: str, profile: ProfileCompletionData, completed: OnboardingProgress
    ) -> None:
        """Reúne la nota del cuestionario y la confirmación de firma leyendo
        el propio progreso ya persistido de los pasos 2 y 3 — ambos guardan
        su resultado en `onboarding_progress.data` al completarse
        (`SubmitQuizUseCase` -> `{"score": ...}`; `SignDocumentUseCase` ->
        `{"document_id": ..., "document_version": ...}`), así que no hace
        falta una consulta nueva a otra tabla para armar el correo de RF
        §2.7."""
        all_steps = await self._repository.list_active_steps()
        progress_by_step_id = {
            p.step_id: p for p in await self._repository.list_progress_for_user(user_id)
        }

        quiz_score: Optional[float] = None
        documents_signed = False
        for onboarding_step in all_steps:
            step_progress = progress_by_step_id.get(onboarding_step.id)
            if step_progress is None or step_progress.status != "completed":
                continue
            if onboarding_step.type == "quiz":
                quiz_score = step_progress.data.get("score")
            elif onboarding_step.type == "signature":
                documents_signed = True

        completed_at = completed.completed_at
        completed_at_label = (
            completed_at.strftime("%d/%m/%Y %H:%M") if completed_at else "—"
        )
        quiz_score_label = f"{quiz_score}%" if quiz_score is not None else "N/D"
        signed_label = "sí" if documents_signed else "no"

        await self._notify.notify_admins(
            type="onboarding_completed",
            title=f"{profile.full_name} completó su onboarding",
            body=(
                f"{profile.full_name} completó el onboarding el {completed_at_label}. "
                f"Nota del cuestionario: {quiz_score_label}. "
                f"Documentos firmados: {signed_label}."
            ),
            data={
                "user_id": user_id,
                "full_name": profile.full_name,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "quiz_score": quiz_score,
                "documents_signed": documents_signed,
                "url": "/administracion/onboarding",
            },
        )
