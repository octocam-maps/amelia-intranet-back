"""
Caso de uso: `GET /onboarding/me` — pasos aplicables al rol del usuario, con
su progreso y el desbloqueo ya calculado. Si el usuario todavía no tiene
filas de progreso (primera visita), las inicializa: el primer paso (por
`step_order`) nace `available`, el resto `locked`.

Esta primera visita es también el "arranque del flujo del trabajador" (RF
§6): si el catálogo aplicable a su rol incluye el paso de documento firmado
(`type='signature'` — el discriminador de tipo no cambió,
sdd/docs-firmados-upload-drive D6, aunque la acción ya no es firmar dentro
de la plataforma sino subir el PDF ya firmado), se dispara
`document_pending_signature` — el documento del paso 3 ya queda registrado
como pendiente de subir desde el minuto uno, aunque el paso todavía esté
`locked` (se desbloquea más adelante, tras vídeo+cuestionario). El
externo-invitado (onboarding parcial, sin este paso —
`docs/permisos-roles.md`) nunca lo dispara: su catálogo aplicable no tiene
ningún paso `signature`.
"""

from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import OnboardingProgress, OnboardingStep
from ...domain.policy import steps_applicable_to_role
from ...domain.ports import IOnboardingRepository


class GetMyOnboardingUseCase:
    def __init__(self, repository: IOnboardingRepository, notify: Optional[NotifyUseCase] = None):
        self._repository = repository
        self._notify = notify

    async def execute(
        self, *, user_id: str, role: str
    ) -> list[tuple[OnboardingStep, OnboardingProgress]]:
        all_steps = await self._repository.list_active_steps()
        applicable_steps = steps_applicable_to_role(all_steps, role)

        # Se comprueba ANTES de inicializar: `ensure_progress_initialized`
        # es idempotente pero se llama en CADA visita a la pantalla — el
        # aviso de "documento pendiente de firma" solo debe dispararse en la
        # primera (progreso todavía vacío), no en cada recarga posterior.
        is_first_visit = not await self._repository.list_progress_for_user(user_id)

        # Idempotente — se puede llamar en cada visita a la pantalla de
        # onboarding sin duplicar ni resetear filas ya existentes.
        await self._repository.ensure_progress_initialized(user_id, applicable_steps)

        if is_first_visit and self._notify is not None:
            await self._notify_pending_signature(user_id, applicable_steps)

        progress_by_step_id = {
            p.step_id: p for p in await self._repository.list_progress_for_user(user_id)
        }

        return [
            (step, progress_by_step_id[step.id])
            for step in applicable_steps
            if step.id in progress_by_step_id
        ]

    async def _notify_pending_signature(
        self, user_id: str, applicable_steps: list[OnboardingStep]
    ) -> None:
        signature_step = next(
            (s for s in applicable_steps if s.type == "signature"), None
        )
        if signature_step is None:
            return

        # Cierre de la carrera de dos "primeras visitas" casi simultáneas
        # (dos pestañas abiertas en el primer login) — mismo criterio de
        # idempotencia que los jobs por-tiempo de `features/notifications`,
        # expuesto aquí vía `NotifyUseCase.already_notified_recipient`. El
        # `type` del catálogo cerrado de 12 notificaciones (RF §6) no
        # cambia — solo el copy, ver sdd/docs-firmados-upload-drive.
        already_notified = await self._notify.already_notified_recipient(
            user_id=user_id,
            type="document_pending_signature",
            data_key="step_id",
            data_value=signature_step.id,
        )
        if already_notified:
            return

        await self._notify.execute(
            recipient_ids=[user_id],
            type="document_pending_signature",
            title="Tienes un documento pendiente de subir",
            body=(
                f'Como parte de tu onboarding, tendrás que subir tu '
                f'documento firmado "{signature_step.title}" en el paso 3.'
            ),
            data={"step_id": signature_step.id, "url": "/onboarding"},
        )
