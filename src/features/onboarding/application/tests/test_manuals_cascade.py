"""
Cascada de lectura de manuales del paso 3 (migración 040, RF-A6.1/RF-A6.3 +
petición del 2026-07-31: el manual de ClickUp se lee obligatoriamente antes de
acceder al resto).

Lo que se protege aquí es el comportamiento que ANTES no existía: el paso 3 era
1:1 paso↔documento y se cerraba con la primera confirmación, simplemente porque
no había más que un manual.
"""

import pytest

from src.features.onboarding.application.use_cases.acknowledge_manual import (
    AcknowledgeManualUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress
from src.features.onboarding.domain.errors import (
    ManualLockedError,
    OnboardingDocumentNotFoundError,
)

from .fakes import FakeOnboardingRepository
from .steps import (
    ALL_STEPS,
    CLICKUP_MANUAL_DOCUMENT,
    MANUAL_DOCUMENT,
    MANUAL_DOCUMENTS,
    MANUAL_STEP,
)

USER = "user-1"


def _repository_with_manual_step_available() -> FakeOnboardingRepository:
    repository = FakeOnboardingRepository(steps=ALL_STEPS, documents=MANUAL_DOCUMENTS)
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
    return repository


async def _acknowledge(repository, document_id=None):
    use_case = AcknowledgeManualUseCase(repository)
    return await use_case.execute(
        user_id=USER,
        role="empleado",
        step_id=MANUAL_STEP.id,
        ip_address="10.0.0.1",
        document_id=document_id,
    )


@pytest.mark.asyncio
async def test_cannot_acknowledge_the_second_manual_before_the_first():
    """La puerta. Vive en el backend porque el candado de la UI es cosmético: un
    POST directo se lo saltaría."""
    repository = _repository_with_manual_step_available()

    with pytest.raises(ManualLockedError) as error:
        await _acknowledge(repository, document_id=MANUAL_DOCUMENT.id)

    # El mensaje nombra el manual que falta, no un genérico "bloqueado": quien lo
    # lee tiene que saber qué hacer a continuación.
    assert "ClickUp" in str(error.value)
    assert repository.acknowledgements == []


@pytest.mark.asyncio
async def test_the_first_manual_of_the_cascade_is_open():
    repository = _repository_with_manual_step_available()

    acknowledgement = await _acknowledge(
        repository, document_id=CLICKUP_MANUAL_DOCUMENT.id
    )

    assert acknowledgement.document_id == CLICKUP_MANUAL_DOCUMENT.id


@pytest.mark.asyncio
async def test_the_step_does_not_close_until_every_manual_is_acknowledged():
    """RF-A6.3. Antes de la 040 el paso se cerraba con la PRIMERA confirmación —
    con dos manuales eso habría dejado pasar al paso 4 sin leer el segundo."""
    repository = _repository_with_manual_step_available()

    await _acknowledge(repository, document_id=CLICKUP_MANUAL_DOCUMENT.id)

    assert repository.progress[(USER, MANUAL_STEP.id)].status == "available"

    await _acknowledge(repository, document_id=MANUAL_DOCUMENT.id)

    assert repository.progress[(USER, MANUAL_STEP.id)].status == "completed"


@pytest.mark.asyncio
async def test_completing_the_step_records_every_manual_read():
    repository = _repository_with_manual_step_available()

    await _acknowledge(repository, document_id=CLICKUP_MANUAL_DOCUMENT.id)
    await _acknowledge(repository, document_id=MANUAL_DOCUMENT.id)

    data = repository.progress[(USER, MANUAL_STEP.id)].data
    assert data["document_ids"] == [CLICKUP_MANUAL_DOCUMENT.id, MANUAL_DOCUMENT.id]


@pytest.mark.asyncio
async def test_acknowledging_the_same_manual_twice_is_idempotent():
    """Doble clic. `document_acknowledgements` tiene UNIQUE (user_id, document_id)
    y el repositorio hace upsert, así que la segunda confirmación no debe crear
    otra fila ni reventar."""
    repository = _repository_with_manual_step_available()

    first = await _acknowledge(repository, document_id=CLICKUP_MANUAL_DOCUMENT.id)
    second = await _acknowledge(repository, document_id=CLICKUP_MANUAL_DOCUMENT.id)

    assert first.id == second.id
    assert len(repository.acknowledgements) == 1
    # Y no cierra el paso: sigue faltando el segundo manual.
    assert repository.progress[(USER, MANUAL_STEP.id)].status == "available"


@pytest.mark.asyncio
async def test_a_client_without_document_id_confirms_the_next_pending_one():
    """Compatibilidad con el cliente anterior a la 040, que hacía este POST SIN
    cuerpo. Romperlo dejaría el paso 3 inutilizable en cualquier pestaña abierta
    durante el despliegue."""
    repository = _repository_with_manual_step_available()

    first = await _acknowledge(repository)
    assert first.document_id == CLICKUP_MANUAL_DOCUMENT.id

    second = await _acknowledge(repository)
    assert second.document_id == MANUAL_DOCUMENT.id
    assert repository.progress[(USER, MANUAL_STEP.id)].status == "completed"


@pytest.mark.asyncio
async def test_an_unknown_document_id_is_not_found_not_locked():
    """Un id que no es un manual activo del paso es 404, no 422: "no existe" y
    "existe pero te falta leer otro antes" son problemas distintos."""
    repository = _repository_with_manual_step_available()

    with pytest.raises(OnboardingDocumentNotFoundError):
        await _acknowledge(repository, document_id="doc-que-no-existe")


@pytest.mark.asyncio
async def test_with_no_manuals_configured_it_is_a_configuration_error():
    repository = FakeOnboardingRepository(steps=ALL_STEPS, documents=[])
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

    with pytest.raises(OnboardingDocumentNotFoundError):
        await _acknowledge(repository)
