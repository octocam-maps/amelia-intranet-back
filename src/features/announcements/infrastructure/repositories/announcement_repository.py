"""
Adaptador asyncpg del puerto `IAnnouncementRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `announcements`
(005_admin_comms.sql).
"""

from datetime import datetime
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import Announcement
from ...domain.ports import IAnnouncementRepository

_SELECT = """
    SELECT
        a.id, a.title, a.body, a.author_id, u.full_name AS author_full_name,
        a.audience, a.entity_id, e.code AS entity_code,
        a.role_id, r.code AS role_code,
        a.is_pinned, a.published_at, a.created_at, a.updated_at
    FROM announcements a
    JOIN users u ON u.id = a.author_id
    LEFT JOIN entities e ON e.id = a.entity_id
    LEFT JOIN roles r ON r.id = a.role_id
    WHERE a.deleted_at IS NULL
"""


def _row_to_announcement(row) -> Announcement:
    return Announcement(
        id=str(row["id"]),
        title=row["title"],
        body=row["body"],
        author_id=str(row["author_id"]),
        author_full_name=row["author_full_name"],
        audience=row["audience"],
        entity_id=str(row["entity_id"]) if row["entity_id"] else None,
        entity_code=row["entity_code"],
        role_id=str(row["role_id"]) if row["role_id"] else None,
        role_code=row["role_code"],
        is_pinned=row["is_pinned"],
        published_at=row["published_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresAnnouncementRepository(IAnnouncementRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_all(self) -> list[Announcement]:
        rows = await self._db.fetch(
            f"{_SELECT} ORDER BY a.is_pinned DESC, a.created_at DESC"
        )
        return [_row_to_announcement(row) for row in rows]

    async def list_feed(
        self, *, role_code: str, entity_id: Optional[str], limit: Optional[int]
    ) -> list[Announcement]:
        query = f"""
            {_SELECT}
              AND a.published_at IS NOT NULL AND a.published_at <= CURRENT_TIMESTAMP
              AND (
                a.audience = 'all'
                OR (a.audience = 'entity' AND a.entity_id = $1)
                OR (a.audience = 'role' AND r.code = $2)
              )
            ORDER BY a.is_pinned DESC, a.published_at DESC
        """
        params: list = [entity_id, role_code]
        if limit is not None:
            query += f" LIMIT ${len(params) + 1}"
            params.append(limit)
        rows = await self._db.fetch(query, *params)
        return [_row_to_announcement(row) for row in rows]

    async def find_by_id(self, announcement_id: str) -> Optional[Announcement]:
        row = await self._db.fetchrow(f"{_SELECT} AND a.id = $1", announcement_id)
        return _row_to_announcement(row) if row else None

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]:
        row = await self._db.fetchval("SELECT id FROM entities WHERE code = $1", entity_code)
        return str(row) if row else None

    async def resolve_role_id(self, role_code: str) -> Optional[str]:
        row = await self._db.fetchval("SELECT id FROM roles WHERE code = $1", role_code)
        return str(row) if row else None

    async def create(
        self,
        *,
        title: str,
        body: str,
        author_id: str,
        audience: str,
        entity_id: Optional[str],
        role_id: Optional[str],
        is_pinned: bool,
        published_at: Optional[datetime],
    ) -> Announcement:
        row = await self._db.fetchrow(
            """
            INSERT INTO announcements
                (title, body, author_id, audience, entity_id, role_id, is_pinned, published_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            title,
            body,
            author_id,
            audience,
            entity_id,
            role_id,
            is_pinned,
            published_at,
        )
        announcement = await self.find_by_id(str(row["id"]))
        assert announcement is not None
        return announcement

    async def update(
        self,
        announcement_id: str,
        *,
        title: Optional[str],
        body: Optional[str],
        audience: Optional[str],
        entity_id: Optional[str],
        role_id: Optional[str],
        clear_entity: bool,
        clear_role: bool,
        is_pinned: Optional[bool],
        published: Optional[bool],
    ) -> Optional[Announcement]:
        # `clear_entity`/`clear_role` fuerzan la columna a NULL cuando la
        # audiencia cambia a algo que ya no la usa — COALESCE por sí solo no
        # puede distinguir "no tocar" de "vaciar".
        found = await self._db.fetchval(
            """
            UPDATE announcements
            SET title = COALESCE($2, title),
                body = COALESCE($3, body),
                audience = COALESCE($4, audience),
                entity_id = CASE WHEN $5 THEN NULL ELSE COALESCE($6, entity_id) END,
                role_id = CASE WHEN $7 THEN NULL ELSE COALESCE($8, role_id) END,
                is_pinned = COALESCE($9, is_pinned),
                published_at = CASE
                    WHEN $10 IS NULL THEN published_at
                    WHEN $10 THEN COALESCE(published_at, CURRENT_TIMESTAMP)
                    ELSE NULL
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND deleted_at IS NULL
            RETURNING id
            """,
            announcement_id,
            title,
            body,
            audience,
            clear_entity,
            entity_id,
            clear_role,
            role_id,
            is_pinned,
            published,
        )
        if found is None:
            return None
        return await self.find_by_id(announcement_id)

    async def soft_delete(self, announcement_id: str) -> bool:
        found = await self._db.fetchval(
            """
            UPDATE announcements SET deleted_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND deleted_at IS NULL
            RETURNING id
            """,
            announcement_id,
        )
        return found is not None
