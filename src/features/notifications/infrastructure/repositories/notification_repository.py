"""
Adaptador asyncpg del puerto `INotificationRepository`. SQL crudo — sin ORM.
Además de `notifications`, hace queries de SOLO LECTURA sobre `users`,
`user_profiles`, `roles` y `time_clock_entries` para resolver destinatarios
de fan-out y alimentar los jobs por-tiempo — mismo patrón que
`features/dashboard/infrastructure/repositories/dashboard_repository.py`.
"""

from datetime import date, datetime
from typing import Any, Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import Notification
from ...domain.ports import INotificationRepository


def _row_to_notification(row) -> Notification:
    return Notification(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        type=row["type"],
        title=row["title"],
        body=row["body"],
        data=row["data"] or {},
        read_at=row["read_at"],
        created_at=row["created_at"],
    )


class PostgresNotificationRepository(INotificationRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def create(
        self, *, user_id: str, type: str, title: str, body: Optional[str], data: dict[str, Any]
    ) -> Notification:
        row = await self._db.fetchrow(
            """
            INSERT INTO notifications (user_id, type, title, body, data)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            user_id,
            type,
            title,
            body,
            data,
        )
        return _row_to_notification(row)

    async def list_for_user(
        self, user_id: str, *, limit: int, before: Optional[datetime]
    ) -> list[Notification]:
        if before is not None:
            rows = await self._db.fetch(
                """
                SELECT * FROM notifications
                WHERE user_id = $1 AND created_at < $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                user_id,
                before,
                limit,
            )
        else:
            rows = await self._db.fetch(
                """
                SELECT * FROM notifications
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
        return [_row_to_notification(row) for row in rows]

    async def count_unread(self, user_id: str) -> int:
        count = await self._db.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE user_id = $1 AND read_at IS NULL",
            user_id,
        )
        return int(count or 0)

    async def mark_read(self, notification_id: str, user_id: str) -> Optional[Notification]:
        # Idempotente: si ya estaba leída, COALESCE conserva su `read_at`
        # original en vez de fallar — releer la misma notificación dos
        # veces no es un error. La condición `user_id = $2` en la propia
        # query es la que impide leer/tocar la notificación de otro (RGPD).
        row = await self._db.fetchrow(
            """
            UPDATE notifications
            SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
            WHERE id = $1 AND user_id = $2
            RETURNING *
            """,
            notification_id,
            user_id,
        )
        return _row_to_notification(row) if row else None

    async def mark_all_read(self, user_id: str) -> int:
        rows = await self._db.fetch(
            """
            UPDATE notifications
            SET read_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND read_at IS NULL
            RETURNING id
            """,
            user_id,
        )
        return len(rows)

    async def find_email(self, user_id: str) -> Optional[str]:
        return await self._db.fetchval(
            "SELECT email FROM users WHERE id = $1 AND deleted_at IS NULL", user_id
        )

    async def list_admin_ids(self) -> list[str]:
        rows = await self._db.fetch(
            """
            SELECT u.id FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE r.code = 'administrador' AND u.status = 'active' AND u.deleted_at IS NULL
            """
        )
        return [str(row["id"]) for row in rows]

    async def list_active_user_ids_excluding_role(self, role_code: str) -> list[str]:
        rows = await self._db.fetch(
            """
            SELECT u.id FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE r.code != $1 AND u.status = 'active' AND u.deleted_at IS NULL
            """,
            role_code,
        )
        return [str(row["id"]) for row in rows]

    async def list_birthday_user_ids(self, *, month: int, day: int) -> list[tuple[str, str]]:
        rows = await self._db.fetch(
            """
            SELECT u.id, u.full_name FROM users u
            JOIN user_profiles p ON p.user_id = u.id
            WHERE p.birth_date IS NOT NULL
              AND EXTRACT(MONTH FROM p.birth_date) = $1
              AND EXTRACT(DAY FROM p.birth_date) = $2
              AND u.status = 'active' AND u.deleted_at IS NULL
            """,
            month,
            day,
        )
        return [(str(row["id"]), row["full_name"]) for row in rows]

    async def list_anniversary_users(self, *, month: int, day: int) -> list[tuple[str, int]]:
        rows = await self._db.fetch(
            """
            SELECT u.id,
                   (EXTRACT(YEAR FROM CURRENT_DATE) - EXTRACT(YEAR FROM u.hire_date))::int AS years
            FROM users u
            WHERE u.hire_date IS NOT NULL
              AND EXTRACT(MONTH FROM u.hire_date) = $1
              AND EXTRACT(DAY FROM u.hire_date) = $2
              AND u.status = 'active' AND u.deleted_at IS NULL
            """,
            month,
            day,
        )
        return [(str(row["id"]), int(row["years"])) for row in rows if row["years"] >= 1]

    async def list_user_ids_with_open_entry(self, work_date: date) -> list[str]:
        rows = await self._db.fetch(
            """
            SELECT DISTINCT user_id FROM time_clock_entries
            WHERE work_date = $1 AND clock_out IS NULL
            """,
            work_date,
        )
        return [str(row["user_id"]) for row in rows]
