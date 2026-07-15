"""
Caso de uso: enviar el cuestionario del paso 2. Corrección SIEMPRE en el
servidor contra `step.config.questions[].correct` — el cliente nunca recibe
la respuesta correcta (ver `GetMyOnboardingUseCase`/mappers, que la
enmascaran en el `GET /onboarding/me`).

Intento único: `create_quiz_attempt` traduce la violación de
`UNIQUE(user_id, step_id)` a `QuizAlreadyAttemptedError` — esa es la
garantía real bajo concurrencia (doble clic, dos pestañas). El chequeo
`find_quiz_attempt` de aquí es solo una salida rápida para el caso NO
concurrente, con un mensaje más claro antes de intentar el INSERT.

Si el intento no alcanza el umbral, el paso NO se completa — y como el
intento ya está consumido, el usuario queda bloqueado en este paso hasta que
el administrador lo reinicie (fuera de alcance de este borrador: no hay
endpoint de reseteo todavía, ver reporte de la feature).
"""

from typing import Any

from ...domain.entities import QuizAttempt
from ...domain.errors import (
    OnboardingStepNotFoundError,
    QuizAlreadyAttemptedError,
    WrongStepTypeError,
)
from ...domain.policy import ensure_step_allowed_for_role, ensure_step_operable
from ...domain.ports import IOnboardingRepository


class SubmitQuizUseCase:
    def __init__(self, repository: IOnboardingRepository):
        self._repository = repository

    async def execute(
        self, *, user_id: str, role: str, step_id: str, answers: dict[str, Any]
    ) -> QuizAttempt:
        step = await self._repository.find_step_by_id(step_id)
        if step is None:
            raise OnboardingStepNotFoundError("El paso de onboarding no existe.")
        if step.type != "quiz":
            raise WrongStepTypeError("Este paso no es de tipo cuestionario.")

        ensure_step_allowed_for_role(step, role)

        current = await self._repository.find_progress(user_id, step_id)
        ensure_step_operable(current)

        existing_attempt = await self._repository.find_quiz_attempt(user_id, step_id)
        if existing_attempt is not None:
            raise QuizAlreadyAttemptedError(
                "Ya has respondido este cuestionario — solo se admite un intento."
            )

        score, passed = self._score(step.config, answers)

        attempt = await self._repository.create_quiz_attempt(
            user_id=user_id,
            step_id=step_id,
            answers=answers,
            score=score,
            passed=passed,
        )

        if passed:
            completed = await self._repository.mark_step_completed_if_operable(
                user_id, step_id, data={"score": score}
            )
            if completed is not None:
                await self._repository.unlock_next_step(user_id, step.step_order)

        return attempt

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
