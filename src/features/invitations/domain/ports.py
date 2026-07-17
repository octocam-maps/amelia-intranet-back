"""
Puerto (Protocol) del feature `invitations`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from datetime import datetime
from typing import Optional, Protocol

from .entities import Invitation


class IInvitationRepository(Protocol):
    async def list_invitations(self, *, status: Optional[str]) -> list[Invitation]:
        """Sin `status`, todas las invitaciones. Con `status='pending'` se
        acota además a `users.status = 'invited'` (ver adaptador): la fila
        `users` ya existe desde el alta EAGER (`staff.create_staff_member`)
        y `invitations.status` nunca transiciona a `'accepted'` en ese flujo
        (deuda conocida, ver design del cambio) — filtrar solo por
        `invitations.status` mostraría como "pendiente" para siempre a
        alguien que ya inició sesión."""
        ...

    async def find_by_id(self, invitation_id: str) -> Optional[Invitation]: ...

    async def update_expiry(self, invitation_id: str, expires_at: datetime) -> Invitation:
        """Extiende `expires_at` (reenvío de una invitación ya vencida)."""
        ...

    async def cancel_invitation(self, invitation_id: str) -> Optional[Invitation]:
        """Marca `invitations.status = 'revoked'` y `users.status =
        'suspended'` en una sola transacción, SOLO si la invitación seguía
        `pending` Y la persona seguía `invited` (no accedió todavía).
        `None` si cualquiera de las dos condiciones ya no se cumplía
        (mismo patrón RACE-safe que
        `absences.update_request_status_if_pending`)."""
        ...
