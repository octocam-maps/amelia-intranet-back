import pytest

from src.features.onboarding.application.use_cases.submit_quiz import SubmitQuizUseCase
from src.features.onboarding.domain.entities import OnboardingProgress
from src.features.onboarding.domain.errors import (
    QuizAlreadyAttemptedError,
    StepNotAvailableForRoleError,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_STEP, QUIZ_STEP


def _repository_with_available_quiz() -> FakeOnboardingRepository:
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
    return repository


_PASSING_ANSWERS = {"q1": "7", "q2": "15s", "q3": "100", "q4": "Starlink"}
_FAILING_ANSWERS = {"q1": "5", "q2": "5s", "q3": "50", "q4": "4G"}


@pytest.mark.asyncio
async def test_passing_score_completes_step_and_unlocks_next():
    repository = _repository_with_available_quiz()
    # El siguiente paso es MANUALES (order 3) desde la reordenación de v1.1 —
    # antes lo era la documentación firmada.
    repository.progress[("user-1", MANUAL_STEP.id)] = OnboardingProgress(
        id="progress-manual",
        user_id="user-1",
        step_id=MANUAL_STEP.id,
        status="locked",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = SubmitQuizUseCase(repository)

    result = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=QUIZ_STEP.id,
        answers=_PASSING_ANSWERS,
    )

    assert result.attempt.passed is True
    assert result.attempt.score == 100.0
    assert result.attempt.attempt_number == 1
    # Aprobado: no hay nada fallado que enseñar y no queda reintento posible
    # (el paso pasa a `completed` y ya no admite envíos).
    assert result.incorrect_question_ids == []
    assert result.attempts_left == 0
    assert repository.progress[("user-1", QUIZ_STEP.id)].status == "completed"
    assert repository.progress[("user-1", MANUAL_STEP.id)].status == "available"


@pytest.mark.asyncio
async def test_failing_score_does_not_complete_step_and_leaves_one_attempt():
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    result = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=QUIZ_STEP.id,
        answers=_FAILING_ANSWERS,
    )

    assert result.attempt.passed is False
    assert result.attempts_used == 1
    assert result.attempts_left == 1
    assert repository.progress[("user-1", QUIZ_STEP.id)].status == "available"


@pytest.mark.asyncio
async def test_devuelve_las_preguntas_falladas_pero_nunca_la_respuesta_correcta():
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    # Falla q2 y q4; acierta q1 y q3.
    result = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=QUIZ_STEP.id,
        answers={"q1": "7", "q2": "5s", "q3": "100", "q4": "4G"},
    )

    assert result.incorrect_question_ids == ["q2", "q4"]
    # Lo que se devuelve son IDS. Ninguna respuesta correcta ("15s",
    # "Starlink") puede aparecer en el resultado: con un segundo intento por
    # delante, filtrarlas lo convertiría en un trámite.
    assert "15s" not in str(result)
    assert "Starlink" not in str(result)


@pytest.mark.asyncio
async def test_una_pregunta_sin_contestar_cuenta_como_fallada():
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    result = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=QUIZ_STEP.id,
        answers={"q1": "7", "q3": "100", "q4": "Starlink"},
    )

    assert result.incorrect_question_ids == ["q2"]


@pytest.mark.asyncio
async def test_el_segundo_intento_si_se_admite_y_puede_aprobar():
    """Cambio de producto (2026-07-29): de un intento a un máximo de dos. Con
    la regla vieja este flujo era imposible — quien fallaba quedaba atascado
    hasta que un admin le reiniciaba el cuestionario a mano."""
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    primero = await use_case.execute(
        user_id="user-1", role="empleado", step_id=QUIZ_STEP.id, answers=_FAILING_ANSWERS
    )
    assert primero.attempt.attempt_number == 1

    segundo = await use_case.execute(
        user_id="user-1", role="empleado", step_id=QUIZ_STEP.id, answers=_PASSING_ANSWERS
    )

    assert segundo.attempt.attempt_number == 2
    assert segundo.attempt.passed is True
    assert segundo.attempts_left == 0
    assert repository.progress[("user-1", QUIZ_STEP.id)].status == "completed"


@pytest.mark.asyncio
async def test_el_tercer_intento_se_rechaza():
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    for _ in range(2):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=QUIZ_STEP.id,
            answers=_FAILING_ANSWERS,
        )

    with pytest.raises(QuizAlreadyAttemptedError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=QUIZ_STEP.id,
            answers=_PASSING_ANSWERS,
        )

    # Agotados los dos intentos sin aprobar, el paso sigue SIN completarse: el
    # trabajador queda aquí hasta que un admin le reinicie el cuestionario.
    assert repository.progress[("user-1", QUIZ_STEP.id)].status == "available"
    assert await repository.count_quiz_attempts("user-1", QUIZ_STEP.id) == 2


@pytest.mark.asyncio
async def test_tras_aprobar_no_se_puede_reintentar_aunque_quede_numero_de_intento():
    """Aprobar en el primer intento deja el paso `completed`, y
    `ensure_step_operable` rechaza cualquier envío posterior — el segundo
    intento existe para recuperarse de un fallo, no para mejorar la nota."""
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    await use_case.execute(
        user_id="user-1", role="empleado", step_id=QUIZ_STEP.id, answers=_PASSING_ANSWERS
    )

    with pytest.raises(Exception) as excinfo:
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=QUIZ_STEP.id, answers=_PASSING_ANSWERS
        )
    assert "completado" in str(excinfo.value)


@pytest.mark.asyncio
async def test_external_guest_cannot_submit_quiz():
    """docs/permisos-roles.md § Onboarding: el externo-invitado no tiene
    cuestionario en su onboarding parcial — se rechaza en el backend aunque
    invoque el endpoint a mano."""
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    with pytest.raises(StepNotAvailableForRoleError):
        await use_case.execute(
            user_id="guest-1",
            role="externo_invitado",
            step_id=QUIZ_STEP.id,
            answers=_PASSING_ANSWERS,
        )

    # Ni siquiera se registró el intento.
    assert await repository.count_quiz_attempts("guest-1", QUIZ_STEP.id) == 0
