"""Entidad de dominio del feature `notifications` (notificaciones in-app,
006_notifications.sql). Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

# Catálogo cerrado de los 12 tipos transaccionales (docs/requerimientos-
# amelia-intranet.pdf §6). Los 8 primeros ya tienen disparador cableado en
# esta fase; los 4 últimos solo se registran aquí — sus features de origen
# (onboarding, documentos/Drive) todavía no existen.
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
        "onboarding_completed",  # FASE 2 — sin disparador todavía
        "document_pending_signature",  # FASE 4 Drive — sin disparador todavía
        "payslip_available",  # FASE 4 Drive — sin disparador todavía
        "document_uploaded",  # FASE 4 Drive — sin disparador todavía
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
