"""Entidad de dominio del feature `mailbox` (buzón anónimo). Sin
dependencias de framework/SQL. El anonimato es estructural: esta entidad
NUNCA lleva user_id, IP ni ningún otro dato que identifique al remitente
(005_admin_comms.sql + 014_mailbox_reply_status.sql)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class AnonymousMessage:
    id: str
    reference_code: str
    category: str
    subject: Optional[str]
    body: str
    status: str
    admin_reply: Optional[str]
    replied_at: Optional[datetime]
    created_at: datetime
