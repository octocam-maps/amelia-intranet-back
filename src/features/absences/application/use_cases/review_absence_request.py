"""
Caso de uso: aprobar o rechazar una solicitud de ausencia (bandeja del
admin, docs/permisos-roles.md § Ausencias). Solo actúa sobre solicitudes en
`pending` — no se admite revisar dos veces la misma solicitud.
"""

from typing import Literal, Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import AbsenceRequest
from ...domain.errors import (
    AbsenceRequestAlreadyReviewedError,
    AbsenceRequestNotFoundError,
    AbsenceTypeNotFoundError,
)
from ...domain.ports import IAbsenceRepository

Decision = Literal["approved", "rejected"]

_TYPE_BY_DECISION = {"approved": "absence_approved", "rejected": "absence_rejected"}
_TITLE_BY_DECISION = {
    "approved": "Tu solicitud de ausencia fue aprobada",
    "rejected": "Tu solicitud de ausencia fue rechazada",
}


class ReviewAbsenceRequestUseCase:
    def __init__(self, repository: IAbsenceRepository, notify: Optional[NotifyUseCase] = None):
        self._repository = repository
        # Opcional para no romper los tests existentes que no lo pasan — sin
        # `notify` el caso de uso sigue funcionando, solo no dispara la
        # notificación (docs/permisos-roles.md § Ausencias).
        self._notify = notify

    async def execute(
        self,
        *,
        request_id: str,
        reviewer_id: str,
        decision: Decision,
        note: Optional[str],
    ) -> AbsenceRequest:
        request = await self._repository.find_request_by_id(request_id)
        if request is None:
            raise AbsenceRequestNotFoundError("La solicitud de ausencia no existe.")
        if request.status != "pending":
            raise AbsenceRequestAlreadyReviewedError(
                "Esta solicitud ya fue revisada — no admite una segunda decisión."
            )

        absence_type = await self._repository.find_type_by_id(request.absence_type_id)
        if absence_type is None:
            raise AbsenceTypeNotFoundError("El tipo de ausencia no existe.")

        # RACE-2 (auditoría QA Fase 3): el UPDATE...WHERE status='pending' es
        # lo que decide de verdad quién "gana" la revisión bajo concurrencia
        # (doble clic, o dos admins aprobando a la vez) — el check de arriba
        # (`request.status != "pending"`) es solo una salida rápida para el
        # caso NO concurrente, no la garantía real de exclusión.
        updated = await self._repository.update_request_status_if_pending(
            request_id, status=decision, reviewed_by=reviewer_id, review_note=note
        )
        if updated is None:
            raise AbsenceRequestAlreadyReviewedError(
                "Esta solicitud ya fue revisada — no admite una segunda decisión."
            )

        # Solo se ajusta el saldo si ESTE UPDATE fue el que ganó la carrera
        # — de lo contrario se duplicaría el ajuste de saldo (RACE-2).
        if absence_type.affects_balance:
            used_delta = request.days_count if decision == "approved" else 0
            await self._repository.adjust_balance(
                request.user_id,
                request.absence_type_id,
                request.start_date.year,
                used_delta=used_delta,
                pending_delta=-request.days_count,
            )

        if self._notify is not None:
            await self._notify.execute(
                recipient_ids=[request.user_id],
                type=_TYPE_BY_DECISION[decision],
                title=_TITLE_BY_DECISION[decision],
                body=note,
                data={"request_id": request_id, "url": "/ausencias"},
            )

        return updated
