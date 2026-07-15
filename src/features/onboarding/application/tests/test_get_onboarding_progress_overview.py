"""
`GET /onboarding/admin/progress` — una fila por usuario (aunque no tenga
progreso inicializado), con `status` derivado de sus filas de progreso y
`total_steps` ajustado a lo que le toca por rol (el externo-invitado hace
onboarding parcial).
"""

from dataclasses import replace

import pytest

from src.features.onboarding.application.use_cases.get_onboarding_progress_overview import (
    GetOnboardingProgressOverviewUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_STEP, QUIZ_STEP, VIDEO_STEP


def _progress(user_id: str, step_id: str, status: str, **overrides) -> OnboardingProgress:
    return OnboardingProgress(
        id=f"progress-{user_id}-{step_id}",
        user_id=user_id,
        step_id=step_id,
        status=status,
        progress_pct=100 if status == "completed" else 0,
        data={},
        started_at=None,
        completed_at=None,
        **overrides,
    )


@pytest.mark.asyncio
async def test_user_without_any_progress_row_is_not_started():
    repository = FakeOnboardingRepository(
        steps=ALL_STEPS,
        users={"user-1": {"full_name": "Ana", "email": "ana@ameliahub.com", "role": "empleado"}},
    )
    use_case = GetOnboardingProgressOverviewUseCase(repository)

    [summary] = await use_case.execute()

    assert summary.status == "not_started"
    assert summary.completed_steps == 0
    assert summary.total_steps == 5
    assert summary.current_step_title is None


@pytest.mark.asyncio
async def test_user_with_all_steps_locked_is_not_started():
    repository = FakeOnboardingRepository(
        steps=ALL_STEPS,
        users={"user-1": {"full_name": "Ana", "email": "ana@ameliahub.com", "role": "empleado"}},
    )
    repository.progress[("user-1", VIDEO_STEP.id)] = _progress(
        "user-1", VIDEO_STEP.id, "locked"
    )
    use_case = GetOnboardingProgressOverviewUseCase(repository)

    [summary] = await use_case.execute()

    assert summary.status == "not_started"


@pytest.mark.asyncio
async def test_user_in_progress_reports_current_step_title():
    repository = FakeOnboardingRepository(
        steps=ALL_STEPS,
        users={"user-1": {"full_name": "Ana", "email": "ana@ameliahub.com", "role": "empleado"}},
    )
    repository.progress[("user-1", VIDEO_STEP.id)] = _progress(
        "user-1", VIDEO_STEP.id, "completed"
    )
    repository.progress[("user-1", QUIZ_STEP.id)] = _progress(
        "user-1", QUIZ_STEP.id, "available"
    )
    use_case = GetOnboardingProgressOverviewUseCase(repository)

    [summary] = await use_case.execute()

    assert summary.status == "in_progress"
    assert summary.completed_steps == 1
    assert summary.current_step_title == QUIZ_STEP.title


@pytest.mark.asyncio
async def test_user_with_all_steps_completed_is_completed_with_no_current_step():
    repository = FakeOnboardingRepository(
        steps=ALL_STEPS,
        users={"user-1": {"full_name": "Ana", "email": "ana@ameliahub.com", "role": "empleado"}},
    )
    for step in ALL_STEPS:
        repository.progress[("user-1", step.id)] = _progress(
            "user-1", step.id, "completed"
        )
    use_case = GetOnboardingProgressOverviewUseCase(repository)

    [summary] = await use_case.execute()

    assert summary.status == "completed"
    assert summary.completed_steps == 5
    assert summary.total_steps == 5
    assert summary.current_step_title is None


@pytest.mark.asyncio
async def test_external_guest_total_steps_is_reduced_and_completes_with_two_steps():
    """docs/permisos-roles.md § Onboarding parcial: el externo-invitado solo
    hace vídeo + manual — no debe quedar eternamente `in_progress` por
    comparar contra los 5 pasos completos."""
    repository = FakeOnboardingRepository(
        steps=ALL_STEPS,
        users={
            "guest-1": {
                "full_name": "Invitado",
                "email": "guest@example.com",
                "role": "externo_invitado",
            }
        },
    )
    repository.progress[("guest-1", VIDEO_STEP.id)] = _progress(
        "guest-1", VIDEO_STEP.id, "completed"
    )
    repository.progress[("guest-1", MANUAL_STEP.id)] = _progress(
        "guest-1", MANUAL_STEP.id, "completed"
    )
    use_case = GetOnboardingProgressOverviewUseCase(repository)

    [summary] = await use_case.execute()

    assert summary.total_steps == 2
    assert summary.status == "completed"


@pytest.mark.asyncio
async def test_returns_one_row_per_user_regardless_of_progress_state():
    repository = FakeOnboardingRepository(
        steps=ALL_STEPS,
        users={
            "user-1": {"full_name": "Ana", "email": "ana@ameliahub.com", "role": "empleado"},
            "user-2": {"full_name": "Luis", "email": "luis@ameliahub.com", "role": "empleado"},
        },
    )
    repository.progress[("user-1", VIDEO_STEP.id)] = _progress(
        "user-1", VIDEO_STEP.id, "in_progress"
    )
    # user-2 nunca visitó /onboarding/me — cero filas de progreso.
    use_case = GetOnboardingProgressOverviewUseCase(repository)

    summaries = await use_case.execute()

    assert {s.user_id for s in summaries} == {"user-1", "user-2"}
    user_2_summary = next(s for s in summaries if s.user_id == "user-2")
    assert user_2_summary.status == "not_started"
