"""
Caso de uso: firmar el documento del paso 3 (firma digital trazable, regla
no negociable §7 del requerimiento). Captura fecha/hora, IP y hash del
documento; el hash de la firma se calcula sobre el documento + usuario +
timestamp, así que se genera aquí (no en la BD) para poder testear el
cálculo sin Postgres.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from ...domain.entities import DocumentSignature
from ...domain.errors import (
    OnboardingDocumentNotFoundError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.policy import ensure_step_allowed_for_role, ensure_step_operable
from ...domain.ports import IOnboardingRepository


class SignDocumentUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        role: str,
        step_id: str,
        ip_address: str,
        user_agent: Optional[str],
    ) -> DocumentSignature:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "signature":
            raise WrongStepTypeError("Este paso no es de tipo firma.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current)

        document = await self._repository.find_active_document("signature")
        if document is None:
            raise OnboardingDocumentNotFoundError(
                "Todavía no hay un documento de firma configurado."
            )

        signed_at = datetime.now(timezone.utc)
        signature_hash = self._compute_signature_hash(
            document_id=document.id,
            document_version=document.version,
            document_hash=document.content_hash,
            user_id=user_id,
            signed_at=signed_at,
        )

        signature = await self._repository.create_signature(
            user_id=user_id,
            document_id=document.id,
            document_version=document.version,
            document_hash=document.content_hash,
            signature_hash=signature_hash,
            signed_at=signed_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        completed = await self._repository.mark_step_completed_if_operable(
            user_id,
            step_id,
            data={"document_id": document.id, "document_version": document.version},
        )
        if completed is not None:
            await self._repository.unlock_next_step(user_id, step.step_order)

        return signature

    @staticmethod
    def _compute_signature_hash(
        *,
        document_id: str,
        document_version: int,
        document_hash: str,
        user_id: str,
        signed_at: datetime,
    ) -> str:
        # sha512 (128 hex chars) para llenar `document_signatures.signature_hash
        # VARCHAR(128)` exactamente — congela documento + versión + hash de
        # contenido + usuario + instante de firma, así queda ligada a este
        # firmante y a este momento, no solo al documento.
        payload = (
            f"{document_id}|{document_version}|{document_hash}"
            f"|{user_id}|{signed_at.isoformat()}"
        )
        return hashlib.sha512(payload.encode("utf-8")).hexdigest()
