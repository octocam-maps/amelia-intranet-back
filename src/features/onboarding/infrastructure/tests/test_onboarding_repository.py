"""
Regresión: el intento único de cuestionario (`UNIQUE(user_id, step_id)` en
`onboarding_quiz_attempts`) debe traducirse a `QuizAlreadyAttemptedError` —
nunca dejar que un 500 genérico llegue al cliente por esta violación.
Mismo patrón de mock de pool que
`features/time_clock/infrastructure/tests/test_time_clock_repository.py`.
"""

from datetime import date
from unittest.mock import AsyncMock

import asyncpg
import pytest

from src.features.onboarding.domain.entities import ProfileCompletionData
from src.features.onboarding.domain.errors import QuizAlreadyAttemptedError
from src.features.onboarding.infrastructure.repositories.onboarding_repository import (
    PostgresOnboardingRepository,
)


def _fake_pool_raising(exc: Exception) -> AsyncMock:
    pool = AsyncMock()
    pool.fetchrow.side_effect = exc
    return pool


def _step_row(**overrides) -> dict:
    row = {
        "id": "step-video",
        "step_order": 1,
        "type": "video",
        "title": "Bienvenida",
        "config": {"url": "/video.mp4", "duration": 96},
        "is_active": True,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_update_step_returns_the_updated_row():
    pool = AsyncMock()
    pool.fetchrow.return_value = _step_row(title="Nuevo título", is_active=False)
    repository = PostgresOnboardingRepository(pool)

    step = await repository.update_step(
        "step-video",
        title="Nuevo título",
        is_active=False,
        config={"url": "/video.mp4", "duration": 96},
    )

    assert step is not None
    assert step.title == "Nuevo título"
    assert step.is_active is False

    query, step_id, title, is_active, config = pool.fetchrow.await_args.args
    assert "UPDATE onboarding_steps" in query
    assert (step_id, title, is_active, config) == (
        "step-video",
        "Nuevo título",
        False,
        {"url": "/video.mp4", "duration": 96},
    )


@pytest.mark.asyncio
async def test_update_step_returns_none_when_step_does_not_exist():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresOnboardingRepository(pool)

    step = await repository.update_step(
        "does-not-exist", title="x", is_active=True, config={}
    )

    assert step is None


@pytest.mark.asyncio
async def test_list_employee_progress_snapshots_groups_rows_by_user():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {
            "user_id": "user-1",
            "full_name": "Ana",
            "email": "ana@ameliahub.com",
            "avatar_url": None,
            "role": "empleado",
            "step_order": 1,
            "step_title": "Bienvenida",
            "step_status": "completed",
        },
        {
            "user_id": "user-1",
            "full_name": "Ana",
            "email": "ana@ameliahub.com",
            "avatar_url": None,
            "role": "empleado",
            "step_order": 2,
            "step_title": "Cuestionario",
            "step_status": "available",
        },
        {
            "user_id": "user-2",
            "full_name": "Luis",
            "email": "luis@ameliahub.com",
            "avatar_url": None,
            "role": "empleado",
            "step_order": None,
            "step_title": None,
            "step_status": None,
        },
    ]
    repository = PostgresOnboardingRepository(pool)

    snapshots = await repository.list_employee_progress_snapshots()

    by_user = {s.user_id: s for s in snapshots}
    assert set(by_user) == {"user-1", "user-2"}
    assert [s.status for s in by_user["user-1"].steps] == ["completed", "available"]
    assert by_user["user-2"].steps == []


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


class _NoOpAsyncContextManager:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *args):
        return False


class _FakeConnection:
    """Espeja una conexión asyncpg dentro de `pool.acquire()` — soporta
    `connection.transaction()` (no-op) más `execute`/`fetchrow` como mocks,
    para probar `reset_quiz_attempt` sin Postgres real."""

    def __init__(self, fetchrow_return=None):
        self.execute = AsyncMock()
        self.fetchrow = AsyncMock(return_value=fetchrow_return)

    def transaction(self):
        return _NoOpAsyncContextManager()


class _FakeAcquireContextManager:
    def __init__(self, connection):
        self._connection = connection

    async def __aenter__(self):
        return self._connection

    async def __aexit__(self, *args):
        return False


class _FakePoolWithConnection:
    def __init__(self, connection: _FakeConnection):
        self._connection = connection

    def acquire(self):
        return _FakeAcquireContextManager(self._connection)


def _progress_row(**overrides) -> dict:
    row = {
        "id": "progress-1",
        "user_id": "user-1",
        "step_id": "step-quiz",
        "status": "available",
        "progress_pct": 0,
        "data": {},
        "started_at": None,
        "completed_at": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_reset_quiz_attempt_deletes_attempt_then_reopens_progress_in_one_transaction():
    connection = _FakeConnection(fetchrow_return=_progress_row())
    pool = _FakePoolWithConnection(connection)
    repository = PostgresOnboardingRepository(pool)

    progress = await repository.reset_quiz_attempt("user-1", "step-quiz")

    assert progress is not None
    assert progress.status == "available"
    assert progress.progress_pct == 0
    assert progress.completed_at is None

    delete_query, delete_user_id, delete_step_id = connection.execute.await_args.args
    assert "DELETE FROM onboarding_quiz_attempts" in delete_query
    assert (delete_user_id, delete_step_id) == ("user-1", "step-quiz")

    update_query = connection.fetchrow.await_args.args[0]
    assert "UPDATE onboarding_progress" in update_query
    assert "SET status = 'available'" in update_query


@pytest.mark.asyncio
async def test_reset_quiz_attempt_returns_none_when_progress_was_never_initialized():
    connection = _FakeConnection(fetchrow_return=None)
    pool = _FakePoolWithConnection(connection)
    repository = PostgresOnboardingRepository(pool)

    progress = await repository.reset_quiz_attempt("user-without-progress", "step-quiz")

    assert progress is None


@pytest.mark.asyncio
async def test_department_exists_returns_true_when_the_row_is_found():
    pool = AsyncMock()
    pool.fetchrow.return_value = {"?column?": 1}
    repository = PostgresOnboardingRepository(pool)

    assert await repository.department_exists("dept-1") is True

    query, department_id = pool.fetchrow.await_args.args
    assert "SELECT 1 FROM departments" in query
    assert department_id == "dept-1"


@pytest.mark.asyncio
async def test_department_exists_returns_false_when_missing():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresOnboardingRepository(pool)

    assert await repository.department_exists("missing-dept") is False


def _profile_completion() -> ProfileCompletionData:
    return ProfileCompletionData(
        full_name="Sandra Ramírez",
        birth_date=date(1990, 5, 20),
        dni_nie="12345678Z",
        personal_phone="+34 600 111 222",
        address="Calle Mayor 1, Madrid",
        department_id="dept-1",
        company_phone=None,
    )


@pytest.mark.asyncio
async def test_save_profile_completion_updates_users_and_upserts_user_profiles_in_one_transaction():
    connection = _FakeConnection(fetchrow_return={"id": "user-1"})
    pool = _FakePoolWithConnection(connection)
    repository = PostgresOnboardingRepository(pool)

    saved = await repository.save_profile_completion("user-1", _profile_completion())

    assert saved is True

    update_query = connection.fetchrow.await_args.args[0]
    assert "UPDATE users" in update_query
    assert "department_id = $3" in update_query

    upsert_query, *upsert_args = connection.execute.await_args.args
    assert "INSERT INTO user_profiles" in upsert_query
    assert "ON CONFLICT (user_id) DO UPDATE" in upsert_query
    assert upsert_args == [
        "user-1",
        "12345678Z",
        date(1990, 5, 20),
        "+34 600 111 222",
        None,
        "Calle Mayor 1, Madrid",
    ]


@pytest.mark.asyncio
async def test_save_profile_completion_returns_false_when_the_user_does_not_exist():
    connection = _FakeConnection(fetchrow_return=None)
    pool = _FakePoolWithConnection(connection)
    repository = PostgresOnboardingRepository(pool)

    saved = await repository.save_profile_completion("missing-user", _profile_completion())

    assert saved is False
    connection.execute.assert_not_called()
