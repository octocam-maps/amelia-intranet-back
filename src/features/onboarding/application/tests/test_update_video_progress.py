from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.features.onboarding.application.use_cases.update_video_progress import (
    UpdateVideoProgressUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress
from src.features.onboarding.domain.errors import (
    InvalidVideoProgressError,
    StepLockedError,
    WrongStepTypeError,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_STEP, QUIZ_STEP, VIDEO_STEP

# `VIDEO_STEP.config["duration"]` (96s) es la base del chequeo de progreso
# real (`ensure_video_progress_matches_elapsed_time`). Los tests que NO
# quieren ejercitar ese chequeo (porque están probando otra regla: el salto
# máximo por request, el desbloqueo del siguiente paso, etc.) simulan que el
# vídeo "ya lleva rato reproduciéndose" empujando `started_at` bien atrás en
# el pasado — así el techo por tiempo nunca es el que rechaza la llamada.
_VIDEO_DURATION = VIDEO_STEP.config["duration"]


def _push_started_at_into_the_past(
    repository: FakeOnboardingRepository, user_id: str, step_id: str, seconds: float
) -> None:
    key = (user_id, step_id)
    repository.progress[key] = replace(
        repository.progress[key],
        started_at=datetime.now(timezone.utc) - timedelta(seconds=seconds),
    )


def _repository_with_available_video() -> FakeOnboardingRepository:
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    repository.progress[("user-1", VIDEO_STEP.id)] = OnboardingProgress(
        id="progress-video",
        user_id="user-1",
        step_id=VIDEO_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    return repository


@pytest.mark.asyncio
async def test_rejects_report_on_a_locked_step():
    """Bloqueo secuencial validado en el backend: aunque se llame al
    endpoint a mano con el step_id del vídeo, si ese paso está `locked`
    (caso hipotético — en la práctica el vídeo siempre nace `available`,
    pero la regla de dominio no debe asumirlo) se rechaza."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    repository.progress[("user-1", VIDEO_STEP.id)] = OnboardingProgress(
        id="progress-video",
        user_id="user-1",
        step_id=VIDEO_STEP.id,
        status="locked",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = UpdateVideoProgressUseCase(repository)

    with pytest.raises(StepLockedError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=10
        )


@pytest.mark.asyncio
async def test_rejects_jump_from_zero_to_hundred():
    """El caso explícito del requerimiento: un salto de golpe de 0 a 100 es
    un intento de saltar el vídeo sin verlo — se rechaza."""
    repository = _repository_with_available_video()
    use_case = UpdateVideoProgressUseCase(repository)

    with pytest.raises(InvalidVideoProgressError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=100
        )

    # No se aplicó ningún cambio.
    assert repository.progress[("user-1", VIDEO_STEP.id)].progress_pct == 0


@pytest.mark.asyncio
async def test_rejects_progress_regression():
    repository = _repository_with_available_video()
    repository.progress[("user-1", VIDEO_STEP.id)] = replace(
        repository.progress[("user-1", VIDEO_STEP.id)],
        progress_pct=50,
        status="in_progress",
    )
    use_case = UpdateVideoProgressUseCase(repository)

    with pytest.raises(InvalidVideoProgressError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=20
        )


@pytest.mark.asyncio
async def test_accepts_gradual_progress_and_completes_at_100_unlocking_next_step():
    repository = _repository_with_available_video()
    repository.progress[("user-1", QUIZ_STEP.id)] = OnboardingProgress(
        id="progress-quiz",
        user_id="user-1",
        step_id=QUIZ_STEP.id,
        status="locked",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = UpdateVideoProgressUseCase(repository)

    # El primer reporte no tiene `started_at` todavía — el chequeo por
    # tiempo real no aplica (lo inicializa el propio repositorio). A partir
    # de ahí, cada llamada empuja `started_at` bien atrás para que el techo
    # por tiempo real nunca sea el que decida: este test ejercita el salto
    # máximo por request y el desbloqueo del siguiente paso, no el chequeo
    # de tiempo real (que tiene su propio test dedicado más abajo).
    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=25
    )
    assert progress.status == "in_progress"

    _push_started_at_into_the_past(repository, "user-1", VIDEO_STEP.id, _VIDEO_DURATION)
    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=50
    )
    assert progress.status == "in_progress"

    _push_started_at_into_the_past(repository, "user-1", VIDEO_STEP.id, _VIDEO_DURATION)
    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=75
    )
    assert progress.status == "in_progress"

    _push_started_at_into_the_past(repository, "user-1", VIDEO_STEP.id, _VIDEO_DURATION)
    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=100
    )
    assert progress.status == "completed"
    assert progress.completed_at is not None

    # El siguiente paso (quiz, order 2) queda desbloqueado.
    quiz_progress = repository.progress[("user-1", QUIZ_STEP.id)]
    assert quiz_progress.status == "available"


@pytest.mark.asyncio
async def test_external_guest_completing_video_unlocks_manual_not_quiz():
    """Regresión: el desbloqueo NO puede asumir `step_order + 1` a secas —
    el externo-invitado no tiene fila de progreso para "quiz" (order 2), así
    que el siguiente paso real tras el vídeo es "manual" (order 4)."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    await repository.ensure_progress_initialized(
        "guest-1",
        [
            VIDEO_STEP,
            MANUAL_STEP,
        ],  # mismo filtrado que aplicaría GetMyOnboardingUseCase
    )
    use_case = UpdateVideoProgressUseCase(repository)

    for index, pct in enumerate((30, 60, 90, 100)):
        if index > 0:
            # Igual que en el test de progreso gradual: se simula que ya
            # pasó tiempo real de sobra entre reportes, para no mezclar el
            # chequeo de tiempo real con lo que este test valida
            # (desbloqueo del paso "manual" para el externo-invitado).
            _push_started_at_into_the_past(
                repository, "guest-1", VIDEO_STEP.id, _VIDEO_DURATION
            )
        await use_case.execute(
            user_id="guest-1",
            role="externo_invitado",
            step_id=VIDEO_STEP.id,
            new_pct=pct,
        )

    manual_progress = repository.progress[("guest-1", MANUAL_STEP.id)]
    assert manual_progress.status == "available"
    assert ("guest-1", QUIZ_STEP.id) not in repository.progress


@pytest.mark.asyncio
async def test_rejects_rapid_fire_reports_that_outpace_real_playback_time():
    """El bypass real (auditoría QA): 4 requests seguidas sin esperar —
    0->29->58->87->100— pasan el chequeo de salto máximo por request (cada
    salto es <=30) pero NO pasan el chequeo de tiempo real: entre una
    request y la siguiente casi no pasa tiempo de reloj, así que el techo
    calculado por `elapsed/duration + margen` las rechaza."""
    repository = _repository_with_available_video()
    use_case = UpdateVideoProgressUseCase(repository)

    # Primer reporte: sin `started_at` todavía, solo se valida el salto por
    # request (29 <= 30) — se acepta y el repositorio fija `started_at=ahora`.
    await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=29
    )

    # Segunda request disparada de inmediato (mismo instante de reloj, en la
    # práctica): el salto (58-29=29) sigue dentro del límite por request,
    # pero el tiempo real transcurrido es ~0s de los 96s del vídeo — muy por
    # debajo de lo que un progreso de 58% justificaría, incluso con margen.
    with pytest.raises(InvalidVideoProgressError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=58
        )

    # No se aplicó el segundo reporte — el progreso se queda en el legítimo.
    assert repository.progress[("user-1", VIDEO_STEP.id)].progress_pct == 29


@pytest.mark.asyncio
async def test_accepts_progress_that_matches_real_elapsed_playback_time():
    """Caso legítimo: el usuario reporta un progreso acorde al tiempo real
    que lleva viendo el vídeo — se acepta aunque no sea el primer reporte."""
    repository = _repository_with_available_video()
    use_case = UpdateVideoProgressUseCase(repository)

    await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=20
    )
    # Han pasado de verdad ~la mitad del vídeo desde el primer reporte (y el
    # salto 20->50 sigue dentro del límite por request, MAX_VIDEO_PROGRESS_JUMP_PCT).
    _push_started_at_into_the_past(
        repository, "user-1", VIDEO_STEP.id, _VIDEO_DURATION / 2
    )

    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=50
    )

    assert progress.progress_pct == 50
    assert progress.status == "in_progress"


@pytest.mark.asyncio
async def test_wrong_step_type_is_rejected():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    repository.progress[("user-1", QUIZ_STEP.id)] = OnboardingProgress(
        id="progress-quiz",
        user_id="user-1",
        step_id=QUIZ_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = UpdateVideoProgressUseCase(repository)

    with pytest.raises(WrongStepTypeError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=QUIZ_STEP.id, new_pct=10
        )
