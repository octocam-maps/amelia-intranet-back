"""Fake en memoria de `IOnboardingRepository` — permite testear los casos de
uso sin Postgres, igual que en `features/absences`/`features/time_clock`."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

from src.features.onboarding.domain.entities import (
    DocumentAcknowledgement,
    DocumentSignature,
    OnboardingDocument,
    OnboardingProgress,
    OnboardingStep,
    QuizAttempt,
)
from src.features.onboarding.domain.errors import QuizAlreadyAttemptedError


class FakeOnboardingRepository:
    def __init__(
        self,
        steps: Optional[list[OnboardingStep]] = None,
        documents: Optional[list[OnboardingDocument]] = None,
    ):
        self.steps: dict[str, OnboardingStep] = {s.id: s for s in (steps or [])}
        self.documents: dict[str, OnboardingDocument] = {
            d.id: d for d in (documents or [])
        }
        self.progress: dict[tuple[str, str], OnboardingProgress] = {}
        self.quiz_attempts: dict[tuple[str, str], QuizAttempt] = {}
        self.signatures: list[DocumentSignature] = []
        self.acknowledgements: list[DocumentAcknowledgement] = []

    async def list_active_steps(self) -> list[OnboardingStep]:
        return sorted(
            (s for s in self.steps.values() if s.is_active), key=lambda s: s.step_order
        )

    async def find_step_by_id(self, step_id: str) -> Optional[OnboardingStep]:
        return self.steps.get(step_id)

    async def list_progress_for_user(self, user_id: str) -> list[OnboardingProgress]:
        return [p for (uid, _), p in self.progress.items() if uid == user_id]

    async def find_progress(
        self, user_id: str, step_id: str
    ) -> Optional[OnboardingProgress]:
        return self.progress.get((user_id, step_id))

    async def ensure_progress_initialized(
        self, user_id: str, steps_in_order: list[OnboardingStep]
    ) -> None:
        for index, step in enumerate(steps_in_order):
            key = (user_id, step.id)
            if key in self.progress:
                continue
            self.progress[key] = OnboardingProgress(
                id=str(uuid.uuid4()),
                user_id=user_id,
                step_id=step.id,
                status="available" if index == 0 else "locked",
                progress_pct=0,
                data={},
                started_at=None,
                completed_at=None,
            )

    async def update_video_progress(
        self, user_id: str, step_id: str, *, new_pct: int
    ) -> Optional[OnboardingProgress]:
        key = (user_id, step_id)
        current = self.progress.get(key)
        if current is None or current.status not in ("available", "in_progress"):
            return None

        now = datetime.now(timezone.utc)
        updated = replace(
            current,
            progress_pct=new_pct,
            status="completed" if new_pct >= 100 else "in_progress",
            started_at=current.started_at or now,
            completed_at=now if new_pct >= 100 else current.completed_at,
        )
        self.progress[key] = updated
        return updated

    async def unlock_next_step(self, user_id: str, completed_step_order: int) -> None:
        # Espeja la CTE de Postgres: el siguiente `locked` con menor
        # `step_order` por encima del completado, DENTRO de las filas de
        # progreso que este usuario ya tiene — no `completed_step_order + 1`
        # a secas (ver comentario en el repositorio real).
        locked_candidates = sorted(
            (
                (self.steps[step_id].step_order, step_id)
                for (uid, step_id), p in self.progress.items()
                if uid == user_id
                and p.status == "locked"
                and self.steps[step_id].step_order > completed_step_order
            )
        )
        if not locked_candidates:
            return
        _, next_step_id = locked_candidates[0]
        key = (user_id, next_step_id)
        self.progress[key] = replace(self.progress[key], status="available")

    async def find_quiz_attempt(
        self, user_id: str, step_id: str
    ) -> Optional[QuizAttempt]:
        return self.quiz_attempts.get((user_id, step_id))

    async def create_quiz_attempt(
        self,
        *,
        user_id: str,
        step_id: str,
        answers: dict[str, Any],
        score: float,
        passed: bool,
    ) -> QuizAttempt:
        key = (user_id, step_id)
        if key in self.quiz_attempts:
            # Espeja la UNIQUE violation real de Postgres (uq_quiz_attempt_single).
            raise QuizAlreadyAttemptedError(
                "Ya has respondido este cuestionario — solo se admite un intento."
            )
        attempt = QuizAttempt(
            id=str(uuid.uuid4()),
            user_id=user_id,
            step_id=step_id,
            answers=answers,
            score=score,
            passed=passed,
            submitted_at=datetime.now(timezone.utc),
        )
        self.quiz_attempts[key] = attempt
        return attempt

    async def mark_step_completed_if_operable(
        self, user_id: str, step_id: str, *, data: dict[str, Any]
    ) -> Optional[OnboardingProgress]:
        key = (user_id, step_id)
        current = self.progress.get(key)
        if current is None or current.status not in ("available", "in_progress"):
            return None

        now = datetime.now(timezone.utc)
        updated = replace(
            current,
            status="completed",
            progress_pct=100,
            data=data,
            started_at=current.started_at or now,
            completed_at=now,
        )
        self.progress[key] = updated
        return updated

    async def find_active_document(self, kind: str) -> Optional[OnboardingDocument]:
        candidates = [
            d for d in self.documents.values() if d.kind == kind and d.is_active
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda d: d.version)

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
        signature = DocumentSignature(
            id=str(uuid.uuid4()),
            user_id=user_id,
            document_id=document_id,
            document_version=document_version,
            document_hash=document_hash,
            signature_hash=signature_hash,
            signed_at=signed_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.signatures.append(signature)
        return signature

    async def create_acknowledgement(
        self, *, user_id: str, document_id: str, ip_address: Optional[str]
    ) -> DocumentAcknowledgement:
        acknowledgement = DocumentAcknowledgement(
            id=str(uuid.uuid4()),
            user_id=user_id,
            document_id=document_id,
            acknowledged_at=datetime.now(timezone.utc),
            ip_address=ip_address,
        )
        self.acknowledgements.append(acknowledgement)
        return acknowledgement
