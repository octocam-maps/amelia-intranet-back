"""
Adaptador asyncpg del puerto `IDocumentRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `employee_documents` y
`drive_sync_runs` (`004_documents.sql`), además de la columna
`users.drive_folder_id` (migración 025, WU-A).

RGPD (docs/CLAUDE.md § reglas no negociables): `list_for_user` SIEMPRE
filtra por `user_id` — el alcance por dueño se decide aquí, nunca solo en
la UI. Todas las consultas de lectura excluyen `deleted_at IS NOT NULL`
(soft-delete, nunca se borra la fila física).
"""

from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.models import Document, SyncRun


def _row_to_document(row) -> Document:
    return Document(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        category=row["category"],
        title=row["title"],
        period=row["period"],
        drive_file_id=row["drive_file_id"],
        mime_type=row["mime_type"],
        content_hash=row["content_hash"],
        uploaded_by=str(row["uploaded_by"]) if row["uploaded_by"] else None,
        uploaded_at=row["uploaded_at"],
        created_at=row["created_at"],
        deleted_at=row["deleted_at"],
    )


def _row_to_sync_run(row) -> SyncRun:
    return SyncRun(
        id=str(row["id"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        status=row["status"],
        files_synced=row["files_synced"],
        error_detail=row["error_detail"],
    )


class PostgresDocumentRepository:
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def find_by_id(self, document_id: str) -> Optional[Document]:
        row = await self._db.fetchrow(
            "SELECT * FROM employee_documents WHERE id = $1 AND deleted_at IS NULL",
            document_id,
        )
        return _row_to_document(row) if row else None

    async def list_for_user(
        self, user_id: str, *, category: Optional[str] = None
    ) -> list[Document]:
        rows = await self._db.fetch(
            """
            SELECT * FROM employee_documents
            WHERE user_id = $1
              AND deleted_at IS NULL
              AND ($2::VARCHAR IS NULL OR category = $2)
            ORDER BY uploaded_at DESC
            """,
            user_id,
            category,
        )
        return [_row_to_document(row) for row in rows]

    async def list_all(
        self, *, category: Optional[str] = None, user_id: Optional[str] = None
    ) -> list[Document]:
        rows = await self._db.fetch(
            """
            SELECT * FROM employee_documents
            WHERE deleted_at IS NULL
              AND ($1::VARCHAR IS NULL OR category = $1)
              AND ($2::UUID IS NULL OR user_id = $2)
            ORDER BY uploaded_at DESC
            """,
            category,
            user_id,
        )
        return [_row_to_document(row) for row in rows]

    async def create(
        self,
        *,
        user_id: str,
        category: str,
        title: str,
        period: Optional[str],
        drive_file_id: Optional[str],
        mime_type: str,
        content_hash: Optional[str],
        uploaded_by: Optional[str],
    ) -> Document:
        row = await self._db.fetchrow(
            """
            INSERT INTO employee_documents (
                user_id, category, title, period, drive_file_id, mime_type,
                content_hash, uploaded_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            user_id,
            category,
            title,
            period,
            drive_file_id,
            mime_type,
            content_hash,
            uploaded_by,
        )
        return _row_to_document(row)

    async def soft_delete(self, document_id: str) -> bool:
        row = await self._db.fetchrow(
            """
            UPDATE employee_documents
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND deleted_at IS NULL
            RETURNING id
            """,
            document_id,
        )
        return row is not None

    async def find_drive_folder_id(self, user_id: str) -> Optional[str]:
        return await self._db.fetchval(
            "SELECT drive_folder_id FROM users WHERE id = $1", user_id
        )

    async def save_drive_folder_id(self, user_id: str, drive_folder_id: str) -> None:
        await self._db.execute(
            "UPDATE users SET drive_folder_id = $2 WHERE id = $1", user_id, drive_folder_id
        )

    async def find_active_users_with_email(self) -> list[tuple[str, str]]:
        # El sync (WU-D) itera SOLO sobre empleados activos — nunca sobre
        # externos-invitados ni usuarios de baja.
        rows = await self._db.fetch("SELECT id, email FROM users WHERE status = 'active'")
        return [(str(row["id"]), row["email"]) for row in rows]

    async def create_sync_run(self) -> SyncRun:
        row = await self._db.fetchrow("INSERT INTO drive_sync_runs DEFAULT VALUES RETURNING *")
        return _row_to_sync_run(row)

    async def finish_sync_run(
        self,
        sync_run_id: str,
        *,
        status: str,
        files_synced: int,
        error_detail: Optional[str],
    ) -> SyncRun:
        row = await self._db.fetchrow(
            """
            UPDATE drive_sync_runs
            SET finished_at = CURRENT_TIMESTAMP, status = $2, files_synced = $3, error_detail = $4
            WHERE id = $1
            RETURNING *
            """,
            sync_run_id,
            status,
            files_synced,
            error_detail,
        )
        return _row_to_sync_run(row)
