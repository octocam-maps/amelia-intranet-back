"""
Caso de uso: confirmar la lectura de los manuales. Menos exigente que la
firma (sin `signature_hash`) — el externo-invitado también hace este paso, es
uno de los dos que su onboarding parcial incluye.

Tras la reordenación de v1.1 (`033_onboarding_steps_reorder_v11.sql`) este
paso es el 3 (antes el 4) y actúa de PUERTA: hasta que no se confirma la
lectura, el trabajador no llega al perfil ni a la documentación que tiene que
descargar, firmar y volver a subir. Es también el ÚLTIMO paso del
externo-invitado (su onboarding parcial es vídeo + manual), y por eso aquí
también se comprueba si el onboarding queda cerrado.

MULTI-MANUAL EN CASCADA (migración 040): el paso admite varios manuales con un
orden de lectura. Dos consecuencias sobre el comportamiento anterior:

  1. Se confirma UN manual concreto (`document_id`), no "el manual" — y solo se
     admite el siguiente pendiente de la cascada (`ensure_manual_unlocked`).
  2. El paso se cierra cuando están TODOS confirmados (RF-A6.3), no con el
     primero. Antes se cerraba con la primera confirmación simplemente porque no
     había más que un manual.
"""

from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import DocumentAcknowledgement
from ...domain.errors import (
    OnboardingDocumentNotFoundError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.policy import (
    are_all_manuals_acknowledged,
    ensure_manual_unlocked,
    ensure_step_allowed_for_role,
    ensure_step_operable,
)
from ...domain.ports import IOnboardingRepository
from .notify_onboarding_completed import NotifyOnboardingCompletedUseCase


def _ordered(documents):
    """Atajo local al orden de la cascada — la regla vive en `domain/policy`."""
    from ...domain.policy import sort_manuals

    return sort_manuals(documents)


class AcknowledgeManualUseCase:
    def __init__(
        self, repository: IOnboardingRepository, notify: Optional[NotifyUseCase] = None
    ):
        self._repository = repository
        self._notify_completion = (
            NotifyOnboardingCompletedUseCase(repository, notify)
            if notify is not None
            else None
        )

    async def execute(
        self,
        *,
        user_id: str,
        role: str,
        step_id: str,
        ip_address: Optional[str],
        document_id: Optional[str] = None,
    ) -> DocumentAcknowledgement:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "manual":
            raise WrongStepTypeError("Este paso no es de tipo manual.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current)

        documents = await self._repository.find_active_documents("manual")
        if not documents:
            raise OnboardingDocumentNotFoundError(
                "Todavía no hay un manual configurado."
            )

        acknowledged_ids = await self._repository.list_acknowledged_document_ids(
            user_id, "manual"
        )

        if document_id is None:
            # Compatibilidad con el cliente anterior a la 040, que confirmaba
            # "el manual" sin decir cuál: se interpreta como "el siguiente
            # pendiente", que es lo único que podía significar cuando había uno.
            target = next(
                (d for d in _ordered(documents) if d.id not in acknowledged_ids),
                None,
            )
            if target is None:
                # Todos confirmados ya: se reconfirma el último para que la
                # petición siga siendo idempotente en vez de dar un error.
                target = _ordered(documents)[-1]
        else:
            if not any(d.id == document_id for d in documents):
                raise OnboardingDocumentNotFoundError(
                    "Ese manual no existe o ya no está activo."
                )
            # La cascada: rechaza saltarse un manual anterior. Reconfirmar uno ya
            # confirmado sí se admite (doble clic).
            target = ensure_manual_unlocked(documents, acknowledged_ids, document_id)

        acknowledgement = await self._repository.create_acknowledgement(
            user_id=user_id, document_id=target.id, ip_address=ip_address
        )

        # El paso NO se cierra hasta que están todos (RF-A6.3). `target.id` se
        # suma a mano en vez de releer la BD: acabamos de escribirlo, y una
        # segunda consulta solo añadiría una ventana de carrera.
        if not are_all_manuals_acknowledged(documents, acknowledged_ids | {target.id}):
            return acknowledgement

        completed = await self._repository.mark_step_completed_if_operable(
            user_id, step_id, data={"document_ids": [d.id for d in _ordered(documents)]}
        )
        if completed is not None:
            await self._repository.unlock_next_step(user_id, step.step_order)

            # Cierra el onboarding del externo-invitado (vídeo + manual). Para
            # empleado/administrador/socio no notifica nada: les quedan el
            # perfil y la documentación, y `is_onboarding_complete` lo ve.
            if self._notify_completion is not None:
                await self._notify_completion.execute(user_id=user_id, role=role)

        return acknowledgement
