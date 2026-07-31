"""
Biblioteca de manuales (`GET /manuals`, migración 043).

Lo que se protege: que la biblioteca sea un SUPERCONJUNTO del paso 3, que no
arrastre la cascada, y que el manual de consulta no se cuele en el onboarding.
"""

import pytest

from src.features.onboarding.application.use_cases.acknowledge_manual import (
    AcknowledgeManualUseCase,
)
from src.features.onboarding.application.use_cases.list_manuals_library import (
    ListManualsLibraryUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress

from .fakes import FakeOnboardingRepository
from .steps import (
    ALL_MANUALS,
    ALL_STEPS,
    CLICKUP_MANUAL_DOCUMENT,
    LIBRARY_MANUAL_DOCUMENT,
    MANUAL_DOCUMENT,
    MANUAL_STEP,
)

USER = "user-1"


def _repository() -> FakeOnboardingRepository:
    return FakeOnboardingRepository(steps=ALL_STEPS, documents=ALL_MANUALS)


@pytest.mark.asyncio
async def test_the_library_includes_the_consultation_only_manual():
    """El manual de uso de la intranet NO está en el paso 3, pero sí en la
    biblioteca: es el motivo de existir de `requires_acknowledgement`."""
    manuals = await ListManualsLibraryUseCase(_repository()).execute(user_id=USER)

    titles = [document.title for document, _ in manuals]
    assert LIBRARY_MANUAL_DOCUMENT.title in titles
    assert len(manuals) == 3


@pytest.mark.asyncio
async def test_the_onboarding_step_does_not_include_the_library_manual():
    """El otro lado del mismo invariante: registrar un manual de consulta NO debe
    alargar la cascada del paso 3 con un manual que nadie pidió leer."""
    repository = _repository()

    cascade = await repository.find_active_documents("manual")

    assert [d.id for d in cascade] == [CLICKUP_MANUAL_DOCUMENT.id, MANUAL_DOCUMENT.id]
    assert LIBRARY_MANUAL_DOCUMENT.id not in [d.id for d in cascade]


@pytest.mark.asyncio
async def test_required_manuals_come_first():
    """El orden refleja "lo que tienes que leer" antes que "lo que puedes
    consultar"."""
    manuals = await ListManualsLibraryUseCase(_repository()).execute(user_id=USER)

    required = [document.requires_acknowledgement for document, _ in manuals]
    assert required == [True, True, False]


@pytest.mark.asyncio
async def test_nothing_is_locked_in_the_library():
    """Sin cascada: la puerta de ClickUp aplica DENTRO del paso 3. Negarle a
    alguien abrir un PDF que necesita para trabajar no protegería nada."""
    manuals = await ListManualsLibraryUseCase(_repository()).execute(user_id=USER)

    # Todos traen su `url` utilizable, sin haber confirmado ninguno.
    assert all(document.storage_ref for document, _ in manuals)


@pytest.mark.asyncio
async def test_marks_what_this_user_already_acknowledged():
    repository = _repository()
    repository.progress[(USER, MANUAL_STEP.id)] = OnboardingProgress(
        id="progress-manual",
        user_id=USER,
        step_id=MANUAL_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    await AcknowledgeManualUseCase(repository).execute(
        user_id=USER,
        role="empleado",
        step_id=MANUAL_STEP.id,
        ip_address=None,
        document_id=CLICKUP_MANUAL_DOCUMENT.id,
    )

    manuals = await ListManualsLibraryUseCase(repository).execute(user_id=USER)

    acknowledged_by_id = {
        document.id: acknowledged for document, acknowledged in manuals
    }
    assert acknowledged_by_id[CLICKUP_MANUAL_DOCUMENT.id] is True
    assert acknowledged_by_id[MANUAL_DOCUMENT.id] is False


@pytest.mark.asyncio
async def test_one_users_reading_progress_is_not_visible_to_another():
    """Los ids confirmados se leen SIEMPRE con el `user_id` de quien pregunta."""
    repository = _repository()
    repository.progress[("otro", MANUAL_STEP.id)] = OnboardingProgress(
        id="progress-otro",
        user_id="otro",
        step_id=MANUAL_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    await AcknowledgeManualUseCase(repository).execute(
        user_id="otro",
        role="empleado",
        step_id=MANUAL_STEP.id,
        ip_address=None,
        document_id=CLICKUP_MANUAL_DOCUMENT.id,
    )

    manuals = await ListManualsLibraryUseCase(repository).execute(user_id=USER)

    assert all(acknowledged is False for _, acknowledged in manuals)


@pytest.mark.asyncio
async def test_an_empty_library_is_not_an_error():
    """Antes de aplicar los seeds no hay manuales. Una lista vacía es una
    respuesta válida, no un 500."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS, documents=[])

    assert await ListManualsLibraryUseCase(repository).execute(user_id=USER) == []
