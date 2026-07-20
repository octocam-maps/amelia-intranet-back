"""Entidad de dominio del feature `notifications` (notificaciones in-app,
006_notifications.sql). Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

# Catálogo cerrado de los 12 tipos transaccionales (docs/requerimientos-
# amelia-intranet.pdf §6). Los 12 tienen disparador cableado:
# `onboarding_completed` en `CompleteProfileUseCase` (paso 5, el último de
# los 5); `document_pending_signature` en `GetMyOnboardingUseCase` (arranque
# del flujo, paso 3); `payslip_available`/`document_uploaded` en
# `UploadDocumentUseCase`/`SyncDocumentsUseCase` (según `category`).
NOTIFICATION_TYPES = frozenset(
    {
        "absence_approved",
        "absence_rejected",
        "absence_requested",
        "announcement_published",
        "mailbox_message",
        "birthday",
        "work_anniversary",
        "clock_out_missing",
        "onboarding_completed",
        "document_pending_signature",
        "payslip_available",
        "document_uploaded",
    }
)


@dataclass(frozen=True)
class Notification:
    id: str
    user_id: str
    type: str
    title: str
    body: Optional[str]
    data: dict[str, Any]
    read_at: Optional[datetime]
    created_at: datetime

    @property
    def read(self) -> bool:
        return self.read_at is not None
