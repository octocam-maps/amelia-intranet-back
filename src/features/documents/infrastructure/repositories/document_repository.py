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

from contextlib import asynccontextmanager
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.models import Document, PendingFolderWork, SyncRun

# Clave del advisory lock del volcado de carpetas. Es un espacio de nombres
# global en Postgres, así que el número tiene que ser único en todo el
# proyecto: si otro trabajo eligiera el mismo, se bloquearían entre sí sin
# ninguna relación aparente. Se anota aquí para que el siguiente que necesite
# uno vea que este está cogido.
_PROVISIONING_LOCK_KEY = 550_001


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

    async def save_drive_folder_id(
        self,
        user_id: str,
        drive_folder_id: str,
        *,
        entity_id: Optional[str] = None,
    ) -> None:
        # `drive_folder_entity_id` [055] deja constancia de bajo qué sociedad
        # quedó la carpeta. Sin ese dato, un cambio de sociedad es indetectable
        # sin preguntar a Drive por cada persona de la plantilla.
        await self._db.execute(
            """
            UPDATE users
               SET drive_folder_id = $2,
                   drive_folder_entity_id = $3
             WHERE id = $1
            """,
            user_id,
            drive_folder_id,
            entity_id,
        )

    async def find_entity_drive_folder_id(self, entity_id: str) -> Optional[str]:
        return await self._db.fetchval(
            "SELECT drive_folder_id FROM entities WHERE id = $1", entity_id
        )

    async def save_entity_drive_folder_id(
        self, entity_id: str, drive_folder_id: str
    ) -> None:
        await self._db.execute(
            "UPDATE entities SET drive_folder_id = $2 WHERE id = $1",
            entity_id,
            drive_folder_id,
        )

    # Única definición de "pendiente" del feature. La comparten
    # `find_pending_folder_work` y `count_pending_folder_work`: si divergieran,
    # la barra de progreso podría no llegar nunca a cero.
    #
    # `IS DISTINCT FROM` y no `<>`: con NULL a ambos lados —el externo-invitado,
    # que no tiene sociedad— `<>` evalúa a NULL, la fila no entra, y esa persona
    # se quedaría fuera del volcado para siempre sin que nada lo delatara.
    _PENDING_FOLDER_WORK_WHERE = """
        WHERE u.status IN ('active', 'invited')
          AND u.deleted_at IS NULL
          AND (u.drive_folder_id IS NULL
               OR u.drive_folder_entity_id IS DISTINCT FROM u.entity_id)
    """

    async def find_pending_folder_work(
        self, *, limit: Optional[int] = None
    ) -> list[PendingFolderWork]:
        rows = await self._db.fetch(
            f"""
            SELECT u.id, u.email, u.entity_id, e.name AS entity_name, u.drive_folder_id
            FROM users u
            LEFT JOIN entities e ON e.id = u.entity_id
            {self._PENDING_FOLDER_WORK_WHERE}
            -- Orden estable: sin él, dos lotes seguidos podrían devolver a la
            -- misma gente y el progreso se estancaría sin motivo aparente.
            ORDER BY u.email
            LIMIT $1
            """,
            limit,
        )
        return [
            PendingFolderWork(
                user_id=str(row["id"]),
                email=row["email"],
                entity_id=str(row["entity_id"]) if row["entity_id"] else None,
                entity_name=row["entity_name"],
                drive_folder_id=row["drive_folder_id"],
            )
            for row in rows
        ]

    async def count_provisionable_users(self) -> int:
        return await self._db.fetchval(
            """
            SELECT COUNT(*) FROM users u
            WHERE u.status IN ('active', 'invited') AND u.deleted_at IS NULL
            """
        )

    async def count_pending_folder_work(self) -> int:
        return await self._db.fetchval(
            f"""
            SELECT COUNT(*) FROM users u
            {self._PENDING_FOLDER_WORK_WHERE}
            """
        )

    @asynccontextmanager
    async def provisioning_lock(self):
        """Advisory lock de sesión: cede `True` si se obtuvo, `False` si ya hay
        otro volcado en curso.

        De SESIÓN y no de transacción porque el lote dura varios segundos
        haciendo llamadas a Drive, y mantener una transacción abierta todo ese
        rato retendría también un slot del pool con una transacción viva.

        Se libera en `finally`, y si el proceso muere sin llegar ahí lo suelta
        Postgres al cerrarse la conexión — no hay cerrojos huérfanos que
        limpiar a mano, que es justo lo que tendría una tabla de "estoy
        ejecutando".
        """
        async with self._db.acquire() as connection:
            acquired = await connection.fetchval(
                "SELECT pg_try_advisory_lock($1)", _PROVISIONING_LOCK_KEY
            )
            try:
                yield acquired
            finally:
                if acquired:
                    await connection.fetchval(
                        "SELECT pg_advisory_unlock($1)", _PROVISIONING_LOCK_KEY
                    )

    async def find_active_users_with_email(self) -> list[tuple[str, str, Optional[str]]]:
        # El sync (WU-D) itera SOLO sobre empleados activos — nunca sobre
        # externos-invitados ni usuarios de baja.
        #
        # `LEFT JOIN` y no `JOIN`: `users.entity_id` admite NULL (el
        # externo-invitado no pertenece a ninguna sociedad) y un JOIN normal
        # lo dejaría fuera del batch sin que nada lo delatara.
        #
        # `deleted_at IS NULL`: a quien se dio de baja definitiva no se le
        # provisiona carpeta nueva.
        rows = await self._db.fetch(
            """
            SELECT u.id, u.email, e.name AS entity_name
            FROM users u
            LEFT JOIN entities e ON e.id = u.entity_id
            WHERE u.status = 'active' AND u.deleted_at IS NULL
            """
        )
        return [(str(row["id"]), row["email"], row["entity_name"]) for row in rows]

    async def find_entity_for_user(
        self, user_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        row = await self._db.fetchrow(
            """
            SELECT e.id, e.name FROM users u
            JOIN entities e ON e.id = u.entity_id
            WHERE u.id = $1
            """,
            user_id,
        )
        return (str(row["id"]), row["name"]) if row else (None, None)

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
