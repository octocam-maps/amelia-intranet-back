"""
Adaptador asyncpg del puerto `IOnboardingRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `onboarding_steps`,
`onboarding_progress`, `onboarding_quiz_attempts`, `onboarding_documents`,
`document_signatures` y `document_acknowledgements` (`002_onboarding.sql`).
"""

from datetime import datetime
from typing import Any, Optional

import asyncpg

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import (
    DocumentAcknowledgement,
    DocumentSignature,
    EmployeeOnboardingSnapshot,
    OnboardingDocument,
    OnboardingProgress,
    OnboardingStep,
    ProfileCompletionData,
    QuizAttempt,
    StepProgressSnapshot,
)
from ...domain.errors import QuizAlreadyAttemptedError
from ...domain.ports import IOnboardingRepository


def _row_to_step(row) -> OnboardingStep:
    return OnboardingStep(
        id=str(row["id"]),
        step_order=row["step_order"],
        type=row["type"],
        title=row["title"],
        config=row["config"],
        is_active=row["is_active"],
    )


def _row_to_progress(row) -> OnboardingProgress:
    return OnboardingProgress(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        step_id=str(row["step_id"]),
        status=row["status"],
        progress_pct=row["progress_pct"],
        data=row["data"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _row_to_quiz_attempt(row) -> QuizAttempt:
    return QuizAttempt(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        step_id=str(row["step_id"]),
        answers=row["answers"],
        score=float(row["score"]),
        passed=row["passed"],
        submitted_at=row["submitted_at"],
    )


def _row_to_document(row) -> OnboardingDocument:
    return OnboardingDocument(
        id=str(row["id"]),
        kind=row["kind"],
        title=row["title"],
        version=row["version"],
        content_hash=row["content_hash"],
        storage_ref=row["storage_ref"],
        is_active=row["is_active"],
    )


def _row_to_signature(row) -> DocumentSignature:
    return DocumentSignature(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        document_id=str(row["document_id"]),
        document_version=row["document_version"],
        document_hash=row["document_hash"],
        signature_hash=row["signature_hash"],
        signed_at=row["signed_at"],
        ip_address=str(row["ip_address"]),
        user_agent=row["user_agent"],
    )


def _row_to_acknowledgement(row) -> DocumentAcknowledgement:
    return DocumentAcknowledgement(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        document_id=str(row["document_id"]),
        acknowledged_at=row["acknowledged_at"],
        ip_address=str(row["ip_address"]) if row["ip_address"] else None,
    )


class PostgresOnboardingRepository(IOnboardingRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_active_steps(self) -> list[OnboardingStep]:
        rows = await self._db.fetch(
            "SELECT * FROM onboarding_steps WHERE is_active = TRUE ORDER BY step_order"
        )
        return [_row_to_step(row) for row in rows]

    async def list_all_steps(self) -> list[OnboardingStep]:
        rows = await self._db.fetch("SELECT * FROM onboarding_steps ORDER BY step_order")
        return [_row_to_step(row) for row in rows]

    async def find_step_by_id(self, step_id: str) -> Optional[OnboardingStep]:
        row = await self._db.fetchrow(
            "SELECT * FROM onboarding_steps WHERE id = $1", step_id
        )
        return _row_to_step(row) if row else None

    async def update_step(
        self, step_id: str, *, title: str, is_active: bool, config: dict[str, Any]
    ) -> Optional[OnboardingStep]:
        row = await self._db.fetchrow(
            """
            UPDATE onboarding_steps
            SET title = $2,
                is_active = $3,
                config = $4,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            RETURNING *
            """,
            step_id,
            title,
            is_active,
            config,
        )
        return _row_to_step(row) if row else None

    async def list_progress_for_user(self, user_id: str) -> list[OnboardingProgress]:
        rows = await self._db.fetch(
            "SELECT * FROM onboarding_progress WHERE user_id = $1", user_id
        )
        return [_row_to_progress(row) for row in rows]

    async def find_progress(
        self, user_id: str, step_id: str
    ) -> Optional[OnboardingProgress]:
        row = await self._db.fetchrow(
            "SELECT * FROM onboarding_progress WHERE user_id = $1 AND step_id = $2",
            user_id,
            step_id,
        )
        return _row_to_progress(row) if row else None

    async def ensure_progress_initialized(
        self, user_id: str, steps_in_order: list[OnboardingStep]
    ) -> None:
        if not steps_in_order:
            return

        # `ON CONFLICT DO NOTHING` sobre `uq_onboarding_progress_user_step`
        # hace este bulk-insert idempotente ante llamadas concurrentes al
        # mismo `GET /onboarding/me` (p.ej. dos pestañas abiertas a la vez).
        rows = [
            (user_id, step.id, "available" if index == 0 else "locked")
            for index, step in enumerate(steps_in_order)
        ]
        async with self._db.acquire() as connection:
            await connection.executemany(
                """
                INSERT INTO onboarding_progress (user_id, step_id, status)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, step_id) DO NOTHING
                """,
                rows,
            )

    async def update_video_progress(
        self, user_id: str, step_id: str, *, new_pct: int
    ) -> Optional[OnboardingProgress]:
        row = await self._db.fetchrow(
            """
            UPDATE onboarding_progress
            SET progress_pct = $3,
                status = CASE WHEN $3 >= 100 THEN 'completed' ELSE 'in_progress' END,
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                completed_at = CASE
                    WHEN $3 >= 100 THEN CURRENT_TIMESTAMP
                    ELSE completed_at
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1
              AND step_id = $2
              AND status IN ('available', 'in_progress')
            RETURNING *
            """,
            user_id,
            step_id,
            new_pct,
        )
        return _row_to_progress(row) if row else None

    async def unlock_next_step(self, user_id: str, completed_step_order: int) -> None:
        # El "siguiente" paso es el `locked` con menor `step_order` por
        # ENCIMA del completado, DENTRO de las filas de progreso que este
        # usuario ya tiene (`ensure_progress_initialized` solo crea filas
        # para los pasos aplicables a su rol) — así el externo-invitado
        # desbloquea "manual" (order 4) al completar "vídeo" (order 1) sin
        # pasar por "quiz" (order 2), que ni siquiera existe para él.
        # `LIMIT 1` + condicionado a `status = 'locked'`: si ya no había
        # nada que desbloquear (era el último paso, o una carrera ya lo
        # desbloqueó), no hace nada.
        await self._db.execute(
            """
            WITH next_locked_step AS (
                SELECT op.id
                FROM onboarding_progress op
                JOIN onboarding_steps os ON os.id = op.step_id
                WHERE op.user_id = $1
                  AND op.status = 'locked'
                  AND os.step_order > $2
                ORDER BY os.step_order ASC
                LIMIT 1
            )
            UPDATE onboarding_progress
            SET status = 'available', updated_at = CURRENT_TIMESTAMP
            WHERE id IN (SELECT id FROM next_locked_step)
            """,
            user_id,
            completed_step_order,
        )

    async def find_quiz_attempt(
        self, user_id: str, step_id: str
    ) -> Optional[QuizAttempt]:
        row = await self._db.fetchrow(
            """
            SELECT * FROM onboarding_quiz_attempts
            WHERE user_id = $1 AND step_id = $2
            """,
            user_id,
            step_id,
        )
        return _row_to_quiz_attempt(row) if row else None

    async def create_quiz_attempt(
        self,
        *,
        user_id: str,
        step_id: str,
        answers: dict[str, Any],
        score: float,
        passed: bool,
    ) -> QuizAttempt:
        try:
            row = await self._db.fetchrow(
                """
                INSERT INTO onboarding_quiz_attempts
                    (user_id, step_id, answers, score, passed)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                user_id,
                step_id,
                answers,
                score,
                passed,
            )
        except asyncpg.exceptions.UniqueViolationError as e:
            # `uq_quiz_attempt_single` es la fuente de verdad real bajo
            # concurrencia (doble clic, dos pestañas) — el chequeo previo del
            # use case (`find_quiz_attempt`) es solo una salida rápida para
            # el caso NO concurrente.
            raise QuizAlreadyAttemptedError(
                "Ya has respondido este cuestionario — solo se admite un intento."
            ) from e
        return _row_to_quiz_attempt(row)

    async def mark_step_completed_if_operable(
        self, user_id: str, step_id: str, *, data: dict[str, Any]
    ) -> Optional[OnboardingProgress]:
        row = await self._db.fetchrow(
            """
            UPDATE onboarding_progress
            SET status = 'completed',
                progress_pct = 100,
                data = $3,
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1
              AND step_id = $2
              AND status IN ('available', 'in_progress')
            RETURNING *
            """,
            user_id,
            step_id,
            data,
        )
        return _row_to_progress(row) if row else None

    async def find_active_document(self, kind: str) -> Optional[OnboardingDocument]:
        row = await self._db.fetchrow(
            """
            SELECT * FROM onboarding_documents
            WHERE kind = $1 AND is_active = TRUE
            ORDER BY version DESC
            LIMIT 1
            """,
            kind,
        )
        return _row_to_document(row) if row else None

    async def create_signature(
        self,
        *,
        user_id: str,
        document_id: str,
        document_version: int,
        document_hash: str,
        signature_hash: str,
        signed_at: datetime,
        ip_address: str,
        user_agent: Optional[str],
    ) -> DocumentSignature:
        row = await self._db.fetchrow(
            """
            INSERT INTO document_signatures
                (user_id, document_id, document_version, document_hash, signature_hash,
                 signed_at, ip_address, user_agent)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            user_id,
            document_id,
            document_version,
            document_hash,
            signature_hash,
            signed_at,
            ip_address,
            user_agent,
        )
        return _row_to_signature(row)

    async def create_acknowledgement(
        self, *, user_id: str, document_id: str, ip_address: Optional[str]
    ) -> DocumentAcknowledgement:
        row = await self._db.fetchrow(
            """
            INSERT INTO document_acknowledgements (user_id, document_id, ip_address)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, document_id) DO UPDATE
                SET acknowledged_at = document_acknowledgements.acknowledged_at
            RETURNING *
            """,
            user_id,
            document_id,
            ip_address,
        )
        return _row_to_acknowledgement(row)

    async def list_employee_progress_snapshots(self) -> list[EmployeeOnboardingSnapshot]:
        # LEFT JOIN: un usuario que nunca llamó a `GET /onboarding/me`
        # aparece con una única fila con `step_id IS NULL` (agrupada abajo
        # en `steps=[]`) — así el panel de admin muestra "no iniciado" en
        # vez de omitirlo.
        rows = await self._db.fetch(
            """
            SELECT
                u.id          AS user_id,
                u.full_name   AS full_name,
                u.email       AS email,
                u.avatar_url  AS avatar_url,
                r.code        AS role,
                os.step_order AS step_order,
                os.title      AS step_title,
                op.status     AS step_status
            FROM users u
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN onboarding_progress op ON op.user_id = u.id
            LEFT JOIN onboarding_steps os ON os.id = op.step_id
            WHERE u.deleted_at IS NULL
              AND r.code IN ('administrador', 'empleado', 'externo_invitado', 'socio')
            ORDER BY u.full_name, os.step_order
            """
        )

        snapshots_by_user: dict[str, EmployeeOnboardingSnapshot] = {}
        for row in rows:
            user_id = str(row["user_id"])
            snapshot = snapshots_by_user.get(user_id)
            if snapshot is None:
                snapshot = EmployeeOnboardingSnapshot(
                    user_id=user_id,
                    full_name=row["full_name"],
                    email=row["email"],
                    avatar_url=row["avatar_url"],
                    role=row["role"],
                    steps=[],
                )
                snapshots_by_user[user_id] = snapshot

            if row["step_order"] is not None:
                snapshot.steps.append(
                    StepProgressSnapshot(
                        step_order=row["step_order"],
                        title=row["step_title"],
                        status=row["step_status"],
                    )
                )

        return list(snapshots_by_user.values())

    async def reset_quiz_attempt(
        self, user_id: str, step_id: str
    ) -> Optional[OnboardingProgress]:
        # Borrado + reapertura en UNA transacción: si el UPDATE de abajo no
        # afecta ninguna fila (usuario sin progreso inicializado en este
        # paso), el DELETE del intento también se revierte — no queremos
        # borrar el intento y dejar el progreso en `completed` a medias.
        async with self._db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    DELETE FROM onboarding_quiz_attempts
                    WHERE user_id = $1 AND step_id = $2
                    """,
                    user_id,
                    step_id,
                )
                row = await connection.fetchrow(
                    """
                    UPDATE onboarding_progress
                    SET status = 'available',
                        progress_pct = 0,
                        data = $3,
                        started_at = NULL,
                        completed_at = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $1 AND step_id = $2
                    RETURNING *
                    """,
                    user_id,
                    step_id,
                    {},
                )
        return _row_to_progress(row) if row else None

    async def department_exists(self, department_id: str) -> bool:
        row = await self._db.fetchrow(
            "SELECT 1 FROM departments WHERE id = $1", department_id
        )
        return row is not None

    async def save_profile_completion(
        self, user_id: str, profile: ProfileCompletionData
    ) -> bool:
        # UNA transacción: identidad/organización (`users`) + ficha
        # personal (`user_profiles`) se escriben juntas o ninguna. UPSERT
        # en `user_profiles` porque puede no haber fila todavía (mismo
        # criterio que `ProfileRepository.update_profile_contact`) — a
        # diferencia de ese PATCH parcial (COALESCE), aquí el paso 5 ya
        # validó que TODOS los campos obligatorios llegaron, así que el
        # UPDATE de la rama de conflicto reemplaza el valor entero, sin
        # COALESCE.
        async with self._db.acquire() as connection:
            async with connection.transaction():
                updated_user = await connection.fetchrow(
                    """
                    UPDATE users
                    SET full_name = $2,
                        department_id = $3,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND deleted_at IS NULL
                    RETURNING id
                    """,
                    user_id,
                    profile.full_name,
                    profile.department_id,
                )
                if updated_user is None:
                    return False

                await connection.execute(
                    """
                    INSERT INTO user_profiles
                        (user_id, dni_nif, birth_date, phone, company_phone,
                         address, completed_at)
                    VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE
                    SET dni_nif = $2,
                        birth_date = $3,
                        phone = $4,
                        company_phone = $5,
                        address = $6,
                        completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    user_id,
                    profile.dni_nie,
                    profile.birth_date,
                    profile.personal_phone,
                    profile.company_phone,
                    profile.address,
                )
        return True
