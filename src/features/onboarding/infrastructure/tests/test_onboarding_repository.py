"""
Regresión: el intento único de cuestionario (`UNIQUE(user_id, step_id)` en
`onboarding_quiz_attempts`) debe traducirse a `QuizAlreadyAttemptedError` —
nunca dejar que un 500 genérico llegue al cliente por esta violación.
Mismo patrón de mock de pool que
`features/time_clock/infrastructure/tests/test_time_clock_repository.py`.
"""

from unittest.mock import AsyncMock

import asyncpg
import pytest

from src.features.onboarding.domain.errors import QuizAlreadyAttemptedError
from src.features.onboarding.infrastructure.repositories.onboarding_repository import (
    PostgresOnboardingRepository,
)


def _fake_pool_raising(exc: Exception) -> AsyncMock:
    pool = AsyncMock()
    pool.fetchrow.side_effect = exc
    return pool


@pytest.mark.asyncio
async def test_create_quiz_attempt_translates_unique_violation_to_domain_error():
    pool = _fake_pool_raising(asyncpg.exceptions.UniqueViolationError("duplicate"))
    repository = PostgresOnboardingRepository(pool)

    with pytest.raises(QuizAlreadyAttemptedError):
        await repository.create_quiz_attempt(
            user_id="user-1",
            step_id="step-quiz",
            answers={"q1": "7"},
            score=100.0,
            passed=True,
        )
