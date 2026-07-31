"""
Caso de uso: enviar el cuestionario del onboarding. Corrección SIEMPRE en el
servidor contra `step.config.questions[].correct` — el cliente nunca recibe la
respuesta correcta (ver `GetMyOnboardingUseCase`/mappers, que la enmascaran en
el `GET /onboarding/me`).

**Dos intentos** (`policy.MAX_QUIZ_ATTEMPTS`, decisión del team-lead del
2026-07-29; antes era uno solo). El chequeo de aquí
(`ensure_quiz_attempts_left`) es la salida rápida con mensaje claro del caso NO
concurrente: dos peticiones simultáneas pueden pasarlo las dos con el mismo
`attempts_used`. La garantía real bajo concurrencia es la UNIQUE de la BD sobre
`(user_id, step_id, attempt_number)`, que hace que solo una de las dos pueda
insertar el intento N — `create_quiz_attempt` traduce esa violación a
`QuizAlreadyAttemptedError`.

Al fallar un intento se devuelven las preguntas erradas, pero como IDS, no como
soluciones: con dos intentos, revelar la respuesta correcta tras el primero
convertiría el segundo en un trámite. El cliente ya tiene los enunciados, así
que con el id puede marcar el fallo.

Si se agotan los intentos sin alcanzar el umbral, el paso NO se completa y el
trabajador queda bloqueado aquí hasta que un administrador le reinicie el
cuestionario (`ResetQuizAttemptUseCase`, que borra los intentos y reabre el
paso).
"""

from typing import Any

from ...domain.entities import QuizSubmissionResult
from ...domain.errors import (
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)
from ...domain.policy import (
    MAX_QUIZ_ATTEMPTS,
    ensure_quiz_attempts_left,
    ensure_step_allowed_for_role,
    ensure_step_operable,
    incorrect_question_ids,
)
from ...domain.ports import IOnboardingRepository


class SubmitQuizUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self, *, user_id: str, role: str, step_id: str, answers: dict[str, Any]
    ) -> QuizSubmissionResult:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "quiz":
            raise WrongStepTypeError("Este paso no es de tipo cuestionario.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current, role)

        attempts_used = await self._repository.count_quiz_attempts(user_id, step_id)
        ensure_quiz_attempts_left(attempts_used)

        score, passed = self._score(step.config, answers)

        attempt = await self._repository.create_quiz_attempt(
            user_id=user_id,
            step_id=step_id,
            answers=answers,
            score=score,
            passed=passed,
            attempt_number=attempts_used + 1,
        )

        if passed:
            completed = await self._repository.mark_step_completed_if_operable(
                user_id, step_id, data={"score": score}
            )
            if completed is not None:
                await self._repository.unlock_next_step(user_id, step.step_order)

        # Se devuelven SIEMPRE, también al aprobar: con un umbral del 70% se
        # puede aprobar fallando una, y saber cuál es información útil sin
        # ninguna contrapartida (son ids, no soluciones, y el paso ya está
        # cerrado). Si el acierto fue pleno, la lista sale vacía sola.
        return QuizSubmissionResult(
            attempt=attempt,
            incorrect_question_ids=incorrect_question_ids(step.config, answers),
            attempts_used=attempt.attempt_number,
            # Aprobar consume el paso: aunque quedara un intento por número, ya
            # no se puede reintentar (el paso pasa a `completed` y
            # `ensure_step_operable` rechaza cualquier envío posterior).
            attempts_left=0 if passed else max(0, MAX_QUIZ_ATTEMPTS - attempt.attempt_number),
        )

    @staticmethod
    def _score(config: dict[str, Any], answers: dict[str, Any]) -> tuple[float, bool]:
        questions = config.get("questions", [])
        threshold = float(config.get("threshold", 1.0))

        if not questions:
            return 0.0, False

        correct_count = sum(
            1
            for question in questions
            if answers.get(question["id"]) == question.get("correct")
        )
        score = round((correct_count / len(questions)) * 100, 2)
        passed = (score / 100) >= threshold
        return score, passed
