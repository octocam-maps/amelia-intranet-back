"""
Servicio de aplicación compartido: avisar a la bandeja de RRHH cuando un
trabajador termina TODO su onboarding (`onboarding_completed`, RF §2.7).

Antes esto vivía dentro de `CompleteProfileUseCase`, que daba el onboarding
por terminado porque el perfil era el paso 5 —"EL ÚLTIMO de los 5", decía su
propio docstring—. La reordenación de v1.1
(`033_onboarding_steps_reorder_v11.sql`) movió el perfil al 4 y la
documentación firmada al 5, así que ese atajo habría notificado
"onboarding completado" con la documentación todavía sin subir.

Ahora el disparador es el ESTADO, no un paso concreto: cada caso de uso que
puede completar el último paso llama aquí, y aquí se comprueba contra el
progreso real (`is_onboarding_complete`) si de verdad ya está todo hecho.
Cuál es "el último paso" depende del rol y del catálogo activo —
empleado/administrador/socio terminan con la documentación firmada, el
externo-invitado con los manuales (su onboarding parcial no tiene ni perfil
ni documentación)— y esta indirección es justamente lo que evita volver a
codificar esa tabla en ningún sitio.

Idempotencia: no hace falta guarda propia. Los casos de uso solo llaman aquí
DESPUÉS de que `mark_step_completed_if_operable` haya devuelto una fila, y
ese UPDATE está condicionado a `status IN ('available','in_progress')` — solo
puede tener éxito una vez por usuario/paso. Por tanto la transición "el
último paso pasa a completed" ocurre exactamente una vez, y con ella este
aviso. (La excepción deliberada es el override de admin
`reset_quiz_attempt`: reabrir un paso ya completado y volver a completarlo
notifica de nuevo, que es lo correcto — el trabajador ha vuelto a terminar.)
"""

from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.policy import is_onboarding_complete, steps_applicable_to_role
from ...domain.ports import IOnboardingRepository


class NotifyOnboardingCompletedUseCase:
    def __init__(self, repository: IOnboardingRepository, notify: NotifyUseCase):
        self._repository = repository
        self._notify = notify

    async def execute(self, *, user_id: str, role: str) -> bool:
        """`True` si el onboarding estaba completo y se notificó; `False` si
        todavía quedan pasos (el caso normal en cada paso intermedio)."""
        all_steps = await self._repository.list_active_steps()
        applicable_steps = steps_applicable_to_role(all_steps, role)
        progress = await self._repository.list_progress_for_user(user_id)

        if not is_onboarding_complete(applicable_steps, progress):
            return False

        progress_by_step_id = {p.step_id: p for p in progress}

        # La nota del cuestionario y la confirmación de documentación se leen
        # del propio `onboarding_progress.data`, donde ya las dejaron sus
        # respectivos casos de uso al completarse (`SubmitQuizUseCase` ->
        # `{"score": ...}`; `UploadSignedOnboardingDocumentUseCase` ->
        # `{"employee_document_id": ...}`) — no hace falta consultar
        # `onboarding_quiz_attempts` ni `employee_documents` otra vez.
        quiz_score: Optional[float] = None
        documents_signed = False
        for step in applicable_steps:
            step_progress = progress_by_step_id.get(step.id)
            if step_progress is None or step_progress.status != "completed":
                continue
            if step.type == "quiz":
                quiz_score = step_progress.data.get("score")
            elif step.type == "signature":
                documents_signed = True

        # Momento de finalización = el `completed_at` MÁS TARDÍO de todos los
        # pasos, no el del paso que dispara esta llamada. Con la reordenación
        # y la renormalización de progreso de la migración 033, el paso que
        # cierra el flujo de un usuario que venía a medias no es
        # necesariamente el de mayor `step_order`.
        completed_ats = [
            p.completed_at for p in progress_by_step_id.values() if p.completed_at
        ]
        completed_at = max(completed_ats) if completed_ats else None
        completed_at_label = (
            completed_at.strftime("%d/%m/%Y %H:%M") if completed_at else "—"
        )

        full_name = await self._repository.find_user_full_name(user_id) or "Un trabajador"
        quiz_score_label = f"{quiz_score}%" if quiz_score is not None else "N/D"
        signed_label = "sí" if documents_signed else "no"

        await self._notify.notify_admins(
            type="onboarding_completed",
            title=f"{full_name} completó su onboarding",
            body=(
                f"{full_name} completó el onboarding el {completed_at_label}. "
                f"Nota del cuestionario: {quiz_score_label}. "
                f"Documentos firmados: {signed_label}."
            ),
            data={
                "user_id": user_id,
                "full_name": full_name,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "quiz_score": quiz_score,
                "documents_signed": documents_signed,
                "url": "/administracion/onboarding",
            },
        )
        return True
