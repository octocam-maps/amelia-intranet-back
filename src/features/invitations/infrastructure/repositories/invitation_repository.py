"""
Adaptador asyncpg del puerto `IInvitationRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `invitations`
(001_core_identity.sql) — cruza además con `users` y `roles` (mismo
acoplamiento cross-feature que ya tiene `staff.staff_repository` y
`auth.user_repository`).
"""

from datetime import datetime
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import Invitation
from ...domain.ports import IInvitationRepository

# `u` = fila `users` de la PERSONA INVITADA, cruzada por email (la fila ya
# existe siempre: el alta es EAGER, `staff.create_staff_member` la crea en
# la misma transacción que `invitations`). `inviter` = fila `users` del
# ADMIN que dio de alta (`invitations.invited_by`, FK real).
_INVITATION_SELECT = """
    SELECT
        i.id, i.email, u.full_name, i.role_id, r.code AS role_code,
        i.entity_id, e.code AS entity_code, i.status, i.expires_at, i.created_at,
        inviter.full_name AS invited_by_name
    FROM invitations i
    JOIN roles r ON r.id = i.role_id
    JOIN users inviter ON inviter.id = i.invited_by
    LEFT JOIN entities e ON e.id = i.entity_id
    LEFT JOIN users u ON u.email = i.email
"""


def _row_to_invitation(row) -> Invitation:
    return Invitation(
        id=str(row["id"]),
        email=row["email"],
        full_name=row["full_name"],
        role_id=str(row["role_id"]),
        role_code=row["role_code"],
        entity_id=str(row["entity_id"]) if row["entity_id"] else None,
        entity_code=row["entity_code"],
        invited_by_name=row["invited_by_name"],
        status=row["status"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
    )


class _CancelAborted(Exception):
    """Señal interna de `cancel_invitation` para forzar el ROLLBACK cuando
    alguna de las dos condiciones de guardia ya no se cumple — se captura
    en el propio método, nunca escapa de este módulo."""


class PostgresInvitationRepository(IInvitationRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_invitations(self, *, status: Optional[str]) -> list[Invitation]:
        query = _INVITATION_SELECT
        params: list = []
        if status:
            params.append(status)
            query += f" WHERE i.status = ${len(params)}"
            # Deuda conocida (ver `domain/ports.py`): `invitations.status`
            # nunca pasa a 'accepted' en el alta EAGER actual — sin este
            # AND, "pendientes" incluiría para siempre a quien ya inició
            # sesión. `u.status = 'invited'` es la señal real de "todavía
            # no accedió".
            if status == "pending":
                query += " AND u.status = 'invited'"
        query += " ORDER BY i.created_at DESC"
        rows = await self._db.fetch(query, *params)
        return [_row_to_invitation(row) for row in rows]

    async def find_by_id(self, invitation_id: str) -> Optional[Invitation]:
        row = await self._db.fetchrow(f"{_INVITATION_SELECT} WHERE i.id = $1", invitation_id)
        return _row_to_invitation(row) if row else None

    async def update_expiry(self, invitation_id: str, expires_at: datetime) -> Invitation:
        await self._db.execute(
            "UPDATE invitations SET expires_at = $2 WHERE id = $1",
            invitation_id,
            expires_at,
        )
        invitation = await self.find_by_id(invitation_id)
        assert invitation is not None
        return invitation

    async def cancel_invitation(self, invitation_id: str) -> Optional[Invitation]:
        try:
            async with self._db.acquire() as connection:
                async with connection.transaction():
                    invitation_row = await connection.fetchrow(
                        """
                        UPDATE invitations SET status = 'revoked'
                        WHERE id = $1 AND status = 'pending'
                        RETURNING email
                        """,
                        invitation_id,
                    )
                    if invitation_row is None:
                        # Ya no estaba `pending` (cancelada dos veces, RACE)
                        # — se aborta con una excepción para que asyncpg
                        # haga ROLLBACK (un `return` normal haría COMMIT).
                        raise _CancelAborted()

                    # Solo se suspende el acceso si la persona seguía sin
                    # haber accedido (`invited`) — si ya está `active`/
                    # `suspended`, esta invitación quedó "pending" para
                    # siempre por la deuda conocida (ver `domain/ports.py`)
                    # y NO se debe tocar su acceso real.
                    user_row = await connection.fetchrow(
                        """
                        UPDATE users SET status = 'suspended', updated_at = CURRENT_TIMESTAMP
                        WHERE email = $1 AND status = 'invited'
                        RETURNING id
                        """,
                        invitation_row["email"],
                    )
                    if user_row is None:
                        raise _CancelAborted()
        except _CancelAborted:
            return None

        return await self.find_by_id(invitation_id)
