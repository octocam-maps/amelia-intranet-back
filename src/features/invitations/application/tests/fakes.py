"""Fakes en memoria de `IInvitationRepository`/`IEmailSender` — permiten
testear los casos de uso sin Postgres (mismo patrón que
`features/staff/application/tests/fakes.py` y
`features/notifications/application/tests/fakes.py`)."""

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.features.invitations.domain.entities import Invitation
from src.shared.email.domain.entities import EmailResult


@dataclass
class _FakeUser:
    email: str
    status: str


class FakeInvitationRepository:
    def __init__(self, invitations: Optional[list[Invitation]] = None):
        self.invitations: dict[str, Invitation] = {i.id: i for i in (invitations or [])}
        # Réplica mínima del estado de `users` (por email) que
        # `cancel_invitation`/el filtro `status='pending'` de
        # `list_invitations` necesitan consultar en Postgres real — por
        # defecto, cada invitación seed asume que la persona sigue
        # `invited` (todavía no ha accedido).
        self.user_status_by_email: dict[str, str] = {
            i.email: "invited" for i in (invitations or [])
        }

    async def list_invitations(self, *, status: Optional[str]) -> list[Invitation]:
        items = list(self.invitations.values())
        if status:
            items = [i for i in items if i.status == status]
            if status == "pending":
                items = [
                    i for i in items if self.user_status_by_email.get(i.email) == "invited"
                ]
        return sorted(items, key=lambda i: i.created_at, reverse=True)

    async def find_by_id(self, invitation_id: str) -> Optional[Invitation]:
        return self.invitations.get(invitation_id)

    async def update_expiry(self, invitation_id: str, expires_at: datetime) -> Invitation:
        updated = replace(self.invitations[invitation_id], expires_at=expires_at)
        self.invitations[invitation_id] = updated
        return updated

    async def cancel_invitation(self, invitation_id: str) -> Optional[Invitation]:
        invitation = self.invitations.get(invitation_id)
        if invitation is None or invitation.status != "pending":
            return None
        if self.user_status_by_email.get(invitation.email) != "invited":
            return None
        cancelled = replace(invitation, status="revoked")
        self.invitations[invitation_id] = cancelled
        self.user_status_by_email[invitation.email] = "suspended"
        return cancelled


def build_invitation(
    *,
    id: Optional[str] = None,
    email: str = "sandra@ameliahub.com",
    full_name: Optional[str] = "Sandra Ramírez",
    role_code: str = "empleado",
    entity_code: Optional[str] = "hub",
    invited_by_name: str = "Beatriz Luna",
    status: str = "pending",
    expires_at: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
) -> Invitation:
    now = datetime.now(timezone.utc)
    return Invitation(
        id=id or str(uuid.uuid4()),
        email=email,
        full_name=full_name,
        role_id=f"role-{role_code}",
        role_code=role_code,
        entity_id=f"entity-{entity_code}" if entity_code else None,
        entity_code=entity_code,
        invited_by_name=invited_by_name,
        status=status,
        expires_at=expires_at or (now + timedelta(days=7)),
        created_at=created_at or now,
    )


class FakeEmailSender:
    """Mismo patrón que `features/staff/application/tests/fakes.py`."""

    def __init__(self, *, fail_for: Optional[set[str]] = None):
        self.sent: list[dict[str, Any]] = []
        self._fail_for = fail_for or set()

    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> EmailResult:
        if to in self._fail_for:
            raise RuntimeError(f"Simulated email failure for {to}")
        self.sent.append({"to": to, "template": template, "context": context, "user_id": user_id})
        return EmailResult(status="sent", provider_message_id=f"fake-{uuid.uuid4()}")
