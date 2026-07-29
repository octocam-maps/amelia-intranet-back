"""Cableado del disparador `onboarding_completed` desde el paso de perfil.

El perfil YA NO es el último paso (reordenación v1.1,
`033_onboarding_steps_reorder_v11.sql`: perfil 4, documentación 5), así que
completarlo solo notifica si con eso queda TODO hecho. La regla en sí vive en
`NotifyOnboardingCompletedUseCase` y tiene su propia suite
(`test_notify_onboarding_completed.py`); aquí se verifica el cableado desde
este caso de uso y que los datos del aviso son los correctos (RF §2.7)."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from src.features.onboarding.application.use_cases.complete_profile import (
    CompleteProfileUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress, ProfileCompletionData

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_STEP, PROFILE_STEP, QUIZ_STEP, SIGNATURE_STEP, VIDEO_STEP


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


def _completed(step_id: str, data: dict | None = None) -> OnboardingProgress:
    now = datetime.now(timezone.utc)
    return OnboardingProgress(
        id=f"progress-{step_id}",
        user_id="user-1",
        step_id=step_id,
        status="completed",
        progress_pct=100,
        data=data or {},
        started_at=now,
        completed_at=now,
    )


def _repository_with_only_the_profile_left(**kwargs) -> FakeOnboardingRepository:
    """Usuario al que solo le falta el perfil: vídeo, cuestionario (nota 75%),
    manuales y documentación ya hechos.

    Ojo con el orden real: la documentación es el paso 5 y el perfil el 4, así
    que este escenario NO es el flujo normal — es el de alguien que venía a
    medias cuando se aplicó la migración 033 y la renormalización de progreso
    le dejó el perfil como único pendiente. Sirve igual para lo que este test
    comprueba: que completar el perfil notifica CUANDO con eso ya está todo.
    Los pasos completados llevan el mismo shape de `data` que dejan sus
    propios casos de uso (`SubmitQuizUseCase`/
    `UploadSignedOnboardingDocumentUseCase`)."""
    kwargs.setdefault("department_ids", {"dept-1"})
    kwargs.setdefault(
        "users",
        {"user-1": {"full_name": "Sandra Ramírez", "email": "s@x.es", "role": "empleado"}},
    )
    repository = FakeOnboardingRepository(steps=ALL_STEPS, **kwargs)
    repository.progress[("user-1", VIDEO_STEP.id)] = _completed(VIDEO_STEP.id)
    repository.progress[("user-1", QUIZ_STEP.id)] = _completed(
        QUIZ_STEP.id, {"score": 75.0}
    )
    repository.progress[("user-1", MANUAL_STEP.id)] = _completed(MANUAL_STEP.id)
    repository.progress[("user-1", SIGNATURE_STEP.id)] = _completed(
        SIGNATURE_STEP.id, {"document_id": "doc-signature", "document_version": 1}
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
async def test_completar_el_perfil_con_la_documentacion_pendiente_no_notifica():
    """El flujo NORMAL tras la reordenación: perfil (4) hecho, documentación
    (5) todavía sin subir. RRHH no debe recibir "onboarding completado" —
    esto es exactamente lo que hacía la lógica vieja, que notificaba aquí
    porque el perfil era el paso 5."""
    repository = _repository_with_only_the_profile_left()
    repository.progress[("user-1", SIGNATURE_STEP.id)] = OnboardingProgress(
        id="progress-signature",
        user_id="user-1",
        step_id=SIGNATURE_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    notify = _RecordingNotify()
    use_case = CompleteProfileUseCase(repository, notify)

    progress = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=PROFILE_STEP.id,
        profile=_valid_profile(),
    )

    # El paso sí se completa: lo que no ocurre es el aviso de finalización.
    assert progress.status == "completed"
    assert notify.admin_calls == []


@pytest.mark.asyncio
async def test_completing_the_last_step_notifies_the_admin_tray():
    repository = _repository_with_only_the_profile_left()
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
    repository = _repository_with_only_the_profile_left()
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
    repository = _repository_with_only_the_profile_left()
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
    repository = _repository_with_only_the_profile_left()
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
