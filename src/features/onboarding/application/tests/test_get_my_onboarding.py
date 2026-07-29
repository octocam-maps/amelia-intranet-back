import pytest

from src.features.onboarding.application.use_cases.get_my_onboarding import (
    GetMyOnboardingUseCase,
)

from .fakes import FakeOnboardingRepository
from .steps import (
    ALL_STEPS,
    MANUAL_DOCUMENT,
    MANUAL_STEP,
    QUIZ_STEP,
    SIGNATURE_STEP,
    VIDEO_STEP,
)


@pytest.mark.asyncio
async def test_los_pasos_con_documento_llegan_con_su_url_real():
    """El cliente no debe hardcodear la ruta del manual ni duplicarla en el
    `config` del paso: `onboarding_documents.storage_ref` es la única fuente de
    verdad de dónde vive el fichero, y llega en el propio paso."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS, documents=[MANUAL_DOCUMENT])
    use_case = GetMyOnboardingUseCase(repository)

    triples = await use_case.execute(user_id="user-1", role="empleado")
    documents_by_step = {step.id: document for step, _, document in triples}

    manual = documents_by_step[MANUAL_STEP.id]
    assert manual is not None
    assert manual.storage_ref == "/manuales/manual-usuario-hincator-2026-ES.pdf"

    # Los pasos sin documento no inventan ninguno.
    assert documents_by_step[VIDEO_STEP.id] is None
    assert documents_by_step[QUIZ_STEP.id] is None
    # La plantilla de documentación todavía no está configurada (RF-A8.4) —
    # `None`, no un error.
    assert documents_by_step[SIGNATURE_STEP.id] is None


@pytest.mark.asyncio
async def test_first_visit_initializes_progress_first_step_available_rest_locked():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    pairs = await use_case.execute(user_id="user-1", role="empleado")

    assert [step.id for step, _, _ in pairs] == [s.id for s in ALL_STEPS]
    statuses = {step.id: progress.status for step, progress, _ in pairs}
    assert statuses[VIDEO_STEP.id] == "available"
    assert all(
        status == "locked"
        for step_id, status in statuses.items()
        if step_id != VIDEO_STEP.id
    )


@pytest.mark.asyncio
async def test_second_visit_does_not_reset_progress():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    await use_case.execute(user_id="user-1", role="empleado")
    # El usuario avanza "a mano" en el fake (simula progreso ya hecho).
    key = ("user-1", VIDEO_STEP.id)
    from dataclasses import replace

    repository.progress[key] = replace(
        repository.progress[key], status="completed", progress_pct=100
    )

    pairs = await use_case.execute(user_id="user-1", role="empleado")
    video_progress = next(p for step, p, _ in pairs if step.id == VIDEO_STEP.id)
    assert video_progress.status == "completed"


@pytest.mark.asyncio
async def test_external_guest_only_gets_video_and_manual_steps():
    """docs/permisos-roles.md § Onboarding: el externo-invitado hace
    onboarding parcial — sin firma, cuestionario ni perfil."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    pairs = await use_case.execute(user_id="guest-1", role="externo_invitado")

    step_ids = {step.id for step, _, _ in pairs}
    assert step_ids == {VIDEO_STEP.id, MANUAL_STEP.id}


@pytest.mark.asyncio
async def test_external_guest_manual_step_starts_locked_video_is_available():
    """El "primero" del externo-invitado (por step_order) es el vídeo — el
    manual (order 4) nace `locked` aunque el cuestionario/firma que están
    entre medias ni siquiera existan para su rol."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    pairs = await use_case.execute(user_id="guest-1", role="externo_invitado")

    statuses = {step.id: progress.status for step, progress, _ in pairs}
    assert statuses[VIDEO_STEP.id] == "available"
    assert statuses[MANUAL_STEP.id] == "locked"
