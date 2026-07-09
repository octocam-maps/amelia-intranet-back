"""
Adaptador asyncpg del puerto `IMailboxRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `anonymous_messages`.

Anonimato estructural (005_admin_comms.sql + 014_mailbox_reply_status.sql):
esta clase NUNCA recibe ni persiste un `user_id`, IP o cualquier dato de la
request — el único identificador de cara al emisor es `reference_code`.
"""

import secrets
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import AnonymousMessage
from ...domain.ports import IMailboxRepository

_STATUS_BY_FILTER = {"unread": "new", "resolved": "resolved"}


def _row_to_message(row) -> AnonymousMessage:
    return AnonymousMessage(
        id=str(row["id"]),
        reference_code=row["reference_code"],
        category=row["category"],
        subject=row["subject"],
        body=row["body"],
        status=row["status"],
        admin_reply=row["admin_reply"],
        replied_at=row["replied_at"],
        created_at=row["created_at"],
    )


class PostgresMailboxRepository(IMailboxRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def create_message(
        self, *, category: str, subject: Optional[str], body: str
    ) -> AnonymousMessage:
        # Reintenta ante una colisión de `reference_code` (extremadamente
        # improbable con 12 hex chars de `secrets.token_hex`, pero la
        # UNIQUE de la BD es la fuente de verdad, no una suposición
        # estadística).
        for _ in range(5):
            reference_code = secrets.token_hex(6).upper()
            row = await self._db.fetchrow(
                """
                INSERT INTO anonymous_messages (reference_code, category, subject, body)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (reference_code) DO NOTHING
                RETURNING *
                """,
                reference_code,
                category,
                subject,
                body,
            )
            if row:
                return _row_to_message(row)
        raise RuntimeError("No se pudo generar un reference_code único tras varios intentos.")

    async def find_by_id(self, message_id: str) -> Optional[AnonymousMessage]:
        row = await self._db.fetchrow("SELECT * FROM anonymous_messages WHERE id = $1", message_id)
        return _row_to_message(row) if row else None

    async def find_by_reference_code(self, reference_code: str) -> Optional[AnonymousMessage]:
        row = await self._db.fetchrow(
            "SELECT * FROM anonymous_messages WHERE reference_code = $1", reference_code
        )
        return _row_to_message(row) if row else None

    async def list_messages(self, *, status_filter: Optional[str]) -> list[AnonymousMessage]:
        status = _STATUS_BY_FILTER.get(status_filter or "")
        if status:
            rows = await self._db.fetch(
                "SELECT * FROM anonymous_messages WHERE status = $1 ORDER BY created_at DESC",
                status,
            )
        else:
            rows = await self._db.fetch("SELECT * FROM anonymous_messages ORDER BY created_at DESC")
        return [_row_to_message(row) for row in rows]

    async def save_reply(self, message_id: str, *, admin_reply: str) -> Optional[AnonymousMessage]:
        # Un mensaje `new` pasa a `read` al responder; si ya estaba
        # `resolved` se deja igual (reabrir es un flujo distinto).
        row = await self._db.fetchrow(
            """
            UPDATE anonymous_messages
            SET admin_reply = $2,
                replied_at = CURRENT_TIMESTAMP,
                status = CASE WHEN status = 'new' THEN 'read' ELSE status END
            WHERE id = $1
            RETURNING *
            """,
            message_id,
            admin_reply,
        )
        return _row_to_message(row) if row else None

    async def mark_resolved(self, message_id: str) -> Optional[AnonymousMessage]:
        row = await self._db.fetchrow(
            "UPDATE anonymous_messages SET status = 'resolved' WHERE id = $1 RETURNING *",
            message_id,
        )
        return _row_to_message(row) if row else None
