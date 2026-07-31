"""Fake en memoria de `IOnboardingRepository` — permite testear los casos de
uso sin Postgres, igual que en `features/absences`/`features/time_clock`."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

from src.features.onboarding.domain.entities import (
    DocumentAcknowledgement,
    EmployeeOnboardingSnapshot,
    OnboardingDocument,
    OnboardingDocumentUpload,
    OnboardingProgress,
    OnboardingStep,
    ProfileCompletionData,
    QuizAttempt,
    StepProgressSnapshot,
)
from src.features.onboarding.domain.errors import QuizAlreadyAttemptedError


class FakeOnboardingRepository:
    def __init__(
        self,
        steps: Optional[list[OnboardingStep]] = None,
        documents: Optional[list[OnboardingDocument]] = None,
        users: Optional[dict[str, dict]] = None,
        department_ids: Optional[set[str]] = None,
        missing_user_ids: Optional[set[str]] = None,
    ):
        self.steps: dict[str, OnboardingStep] = {s.id: s for s in (steps or [])}
        self.documents: dict[str, OnboardingDocument] = {
            d.id: d for d in (documents or [])
        }
        self.progress: dict[tuple[str, str], OnboardingProgress] = {}
        # Clave (user_id, step_id, attempt_number) — espeja
        # `uq_quiz_attempt_per_number`, no la vieja UNIQUE(user_id, step_id).
        self.quiz_attempts: dict[tuple[str, str, int], QuizAttempt] = {}
        self.document_uploads: list[OnboardingDocumentUpload] = []
        self.acknowledgements: list[DocumentAcknowledgement] = []
        # user_id -> {full_name, email, avatar_url, role} — solo lo que
        # necesita `list_employee_progress_snapshots` (panel de admin).
        self.users: dict[str, dict] = users or {}
        # Departamentos "existentes" para `department_exists` — el paso 5
        # valida la referencia antes de escribirla.
        self.department_ids: set[str] = set(department_ids or set())
        # user_id simulados como "no existe/borrado" — para probar la rama
        # defensiva de `save_profile_completion`.
        self.missing_user_ids: set[str] = set(missing_user_ids or set())
        self.saved_profiles: dict[str, ProfileCompletionData] = {}

    async def list_active_steps(self) -> list[OnboardingStep]:
        return sorted(
            (s for s in self.steps.values() if s.is_active), key=lambda s: s.step_order
        )

    async def list_all_steps(self) -> list[OnboardingStep]:
        return sorted(self.steps.values(), key=lambda s: s.step_order)

    async def find_step_by_id(self, step_id: str) -> Optional[OnboardingStep]:
        return self.steps.get(step_id)

    async def update_step(
        self, step_id: str, *, title: str, is_active: bool, config: dict[str, Any]
    ) -> Optional[OnboardingStep]:
        current = self.steps.get(step_id)
        if current is None:
            return None
        updated = replace(current, title=title, is_active=is_active, config=config)
        self.steps[step_id] = updated
        return updated

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
        attempts = self._attempts_for(user_id, step_id)
        if not attempts:
            return None
        return max(attempts, key=lambda a: a.attempt_number)

    async def count_quiz_attempts(self, user_id: str, step_id: str) -> int:
        return len(self._attempts_for(user_id, step_id))

    def _attempts_for(self, user_id: str, step_id: str) -> list[QuizAttempt]:
        return [
            attempt
            for (uid, sid, _), attempt in self.quiz_attempts.items()
            if uid == user_id and sid == step_id
        ]

    async def create_quiz_attempt(
        self,
        *,
        user_id: str,
        step_id: str,
        answers: dict[str, Any],
        score: float,
        passed: bool,
        attempt_number: int,
    ) -> QuizAttempt:
        key = (user_id, step_id, attempt_number)
        if key in self.quiz_attempts:
            # Espeja la UNIQUE violation real de Postgres
            # (`uq_quiz_attempt_per_number`): la colisión es por NÚMERO de
            # intento, no por usuario/paso — es lo que impide que dos envíos
            # simultáneos consuman el mismo intento.
            raise QuizAlreadyAttemptedError(
                "Otro envío de este cuestionario se registró antes que el tuyo — "
                "recarga la página para ver tu resultado."
            )
        attempt = QuizAttempt(
            id=str(uuid.uuid4()),
            user_id=user_id,
            step_id=step_id,
            answers=answers,
            score=score,
            passed=passed,
            submitted_at=datetime.now(timezone.utc),
            attempt_number=attempt_number,
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

    async def find_active_documents(self, kind: str) -> list[OnboardingDocument]:
        # Mismo orden que `PostgresOnboardingRepository`: `display_order` ASC
        # (la cascada de la 040) y `version` DESC como desempate.
        candidates = [
            d for d in self.documents.values() if d.kind == kind and d.is_active
        ]
        return sorted(candidates, key=lambda d: (d.display_order, -d.version))

    async def list_acknowledged_document_ids(self, user_id: str, kind: str) -> set[str]:
        return {
            a.document_id
            for a in self.acknowledgements
            if a.user_id == user_id
            and (doc := self.documents.get(a.document_id)) is not None
            and doc.kind == kind
        }

    async def create_document_upload(
        self, *, user_id: str, onboarding_document_id: str, employee_document_id: str
    ) -> OnboardingDocumentUpload:
        upload = OnboardingDocumentUpload(
            id=str(uuid.uuid4()),
            user_id=user_id,
            onboarding_document_id=onboarding_document_id,
            employee_document_id=employee_document_id,
            uploaded_at=datetime.now(timezone.utc),
        )
        self.document_uploads.append(upload)
        return upload

    async def create_acknowledgement(
        self, *, user_id: str, document_id: str, ip_address: Optional[str]
    ) -> DocumentAcknowledgement:
        # `document_acknowledgements` tiene UNIQUE (user_id, document_id) y el
        # repositorio real hace upsert: reconfirmar NO crea una segunda fila.
        existing = next(
            (
                a
                for a in self.acknowledgements
                if a.user_id == user_id and a.document_id == document_id
            ),
            None,
        )
        if existing is not None:
            return existing
        acknowledgement = DocumentAcknowledgement(
            id=str(uuid.uuid4()),
            user_id=user_id,
            document_id=document_id,
            acknowledged_at=datetime.now(timezone.utc),
            ip_address=ip_address,
        )
        self.acknowledgements.append(acknowledgement)
        return acknowledgement

    async def list_employee_progress_snapshots(self) -> list[EmployeeOnboardingSnapshot]:
        snapshots = []
        for user_id, info in self.users.items():
            steps = sorted(
                (
                    StepProgressSnapshot(
                        step_order=self.steps[step_id].step_order,
                        title=self.steps[step_id].title,
                        status=progress.status,
                    )
                    for (uid, step_id), progress in self.progress.items()
                    if uid == user_id
                ),
                key=lambda s: s.step_order,
            )
            snapshots.append(
                EmployeeOnboardingSnapshot(
                    user_id=user_id,
                    full_name=info["full_name"],
                    email=info["email"],
                    avatar_url=info.get("avatar_url"),
                    role=info["role"],
                    steps=steps,
                )
            )
        return snapshots

    async def reset_quiz_attempt(
        self, user_id: str, step_id: str
    ) -> Optional[OnboardingProgress]:
        # Borra TODOS los intentos de este usuario/paso, no solo el primero —
        # espeja el `DELETE ... WHERE user_id = $1 AND step_id = $2` real, que
        # no filtra por `attempt_number`.
        for key in [
            k for k in self.quiz_attempts if k[0] == user_id and k[1] == step_id
        ]:
            del self.quiz_attempts[key]

        key = (user_id, step_id)
        current = self.progress.get(key)
        if current is None:
            return None

        updated = replace(
            current,
            status="available",
            progress_pct=0,
            data={},
            started_at=None,
            completed_at=None,
        )
        self.progress[key] = updated
        return updated

    async def department_exists(self, department_id: str) -> bool:
        return department_id in self.department_ids

    async def find_user_full_name(self, user_id: str) -> Optional[str]:
        if user_id in self.missing_user_ids:
            return None
        # `save_profile_completion` es la vía por la que el nombre llega de
        # verdad a `users` — si el paso de perfil ya se completó en este
        # escenario, ese nombre gana sobre el sembrado en `users`.
        saved = self.saved_profiles.get(user_id)
        if saved is not None:
            return saved.full_name
        info = self.users.get(user_id)
        return info.get("full_name") if info else None

    async def save_profile_completion(
        self, user_id: str, profile: ProfileCompletionData
    ) -> bool:
        if user_id in self.missing_user_ids:
            return False
        self.saved_profiles[user_id] = profile
        return True
