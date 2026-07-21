"""Cableado del disparador `onboarding_completed` — al completar el paso 5
("Completar perfil", el último de los 5) se notifica a la bandeja del admin
con nombre, fecha/hora de finalización, nota del cuestionario y confirmación
de documentos firmados (RF §2.7). `NotifyUseCase.notify_admins` en sí ya
tiene su propia suite en `features/notifications`; aquí solo se verifica que
`CompleteProfileUseCase` la invoca con los datos correctos."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from src.features.onboarding.application.use_cases.complete_profile import (
    CompleteProfileUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress, ProfileCompletionData

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, PROFILE_STEP, QUIZ_STEP, SIGNATURE_STEP


class _RecordingNotify:
    def __init__(self):
        self.admin_calls: list[dict] = []

    async def notify_admins(self, **kwargs):
        self.admin_calls.append(kwargs)


def _valid_profile(**overrides) -> ProfileCompletionData:
    defaults = dict(
        full_name="Sandra Ramírez",
        birth_date=date(1990, 5, 20),
        dni_nie="12345678Z",
        personal_phone="+34 600 111 222",
        address="Calle Mayor 1, Madrid",
        department_id="dept-1",
        company_phone=None,
    )
    defaults.update(overrides)
    return ProfileCompletionData(**defaults)


def _repository_with_full_flow_completed(**kwargs) -> FakeOnboardingRepository:
    """Simula un usuario que ya completó vídeo, cuestionario (nota 75%) y
    la subida del documento firmado — solo le falta el paso 5. Los pasos
    2/3 quedan `completed` con el mismo shape de `data` que dejan sus
    propios use cases (`SubmitQuizUseCase`/
    `UploadSignedOnboardingDocumentUseCase`)."""
    kwargs.setdefault("department_ids", {"dept-1"})
    repository = FakeOnboardingRepository(steps=ALL_STEPS, **kwargs)
    now = datetime.now(timezone.utc)
    repository.progress[("user-1", QUIZ_STEP.id)] = OnboardingProgress(
        id="progress-quiz",
        user_id="user-1",
        step_id=QUIZ_STEP.id,
        status="completed",
        progress_pct=100,
        data={"score": 75.0},
        started_at=now,
        completed_at=now,
    )
    repository.progress[("user-1", SIGNATURE_STEP.id)] = OnboardingProgress(
        id="progress-signature",
        user_id="user-1",
        step_id=SIGNATURE_STEP.id,
        status="completed",
        progress_pct=100,
        data={"document_id": "doc-signature", "document_version": 1},
        started_at=now,
        completed_at=now,
    )
    repository.progress[("user-1", PROFILE_STEP.id)] = OnboardingProgress(
        id="progress-profile",
        user_id="user-1",
        step_id=PROFILE_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    return repository


@pytest.mark.asyncio
async def test_completing_the_last_step_notifies_the_admin_tray():
    repository = _repository_with_full_flow_completed()
    notify = _RecordingNotify()
    use_case = CompleteProfileUseCase(repository, notify)

    await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=PROFILE_STEP.id,
        profile=_valid_profile(),
    )

    assert len(notify.admin_calls) == 1
    call = notify.admin_calls[0]
    assert call["type"] == "onboarding_completed"
    assert call["data"]["full_name"] == "Sandra Ramírez"
    assert call["data"]["quiz_score"] == 75.0
    assert call["data"]["documents_signed"] is True
    assert call["data"]["completed_at"] is not None


@pytest.mark.asyncio
async def test_notification_reflects_the_actual_quiz_score():
    repository = _repository_with_full_flow_completed()
    repository.progress[("user-1", QUIZ_STEP.id)] = replace(
        repository.progress[("user-1", QUIZ_STEP.id)], data={"score": 50.0}
    )
    notify = _RecordingNotify()
    use_case = CompleteProfileUseCase(repository, notify)

    await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=PROFILE_STEP.id,
        profile=_valid_profile(),
    )

    assert notify.admin_calls[0]["data"]["quiz_score"] == 50.0
    assert "50.0%" in notify.admin_calls[0]["body"]


@pytest.mark.asyncio
async def test_complete_profile_without_a_notify_dependency_still_works():
    repository = _repository_with_full_flow_completed()
    use_case = CompleteProfileUseCase(repository)

    progress = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=PROFILE_STEP.id,
        profile=_valid_profile(),
    )

    assert progress.status == "completed"


@pytest.mark.asyncio
async def test_a_failed_validation_does_not_notify_the_admin_tray():
    repository = _repository_with_full_flow_completed()
    notify = _RecordingNotify()
    use_case = CompleteProfileUseCase(repository, notify)

    with pytest.raises(Exception):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(full_name=""),
        )

    assert notify.admin_calls == []
