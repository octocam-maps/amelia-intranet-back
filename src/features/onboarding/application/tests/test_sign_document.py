import pytest

from src.features.onboarding.application.use_cases.sign_document import (
    SignDocumentUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress
from src.features.onboarding.domain.errors import (
    OnboardingDocumentNotFoundError,
    StepLockedError,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, SIGNATURE_DOCUMENT, SIGNATURE_STEP


def _repository_with_available_signature(
    *, with_document: bool = True
) -> FakeOnboardingRepository:
    documents = [SIGNATURE_DOCUMENT] if with_document else []
    repository = FakeOnboardingRepository(steps=ALL_STEPS, documents=documents)
    repository.progress[("user-1", SIGNATURE_STEP.id)] = OnboardingProgress(
        id="progress-signature",
        user_id="user-1",
        step_id=SIGNATURE_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    return repository


@pytest.mark.asyncio
async def test_signing_captures_trace_fields_and_completes_step():
    """Firma digital trazable (regla no negociable §7): fecha/hora, IP y
    hash del documento congelado en el momento de firmar."""
    repository = _repository_with_available_signature()
    use_case = SignDocumentUseCase(repository)

    signature = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=SIGNATURE_STEP.id,
        ip_address="203.0.113.7",
        user_agent="pytest-agent",
    )

    assert signature.ip_address == "203.0.113.7"
    assert signature.document_hash == SIGNATURE_DOCUMENT.content_hash
    assert signature.document_version == SIGNATURE_DOCUMENT.version
    assert len(signature.signature_hash) == 128  # sha512 hex
    assert repository.progress[("user-1", SIGNATURE_STEP.id)].status == "completed"


@pytest.mark.asyncio
async def test_two_signatures_of_the_same_document_have_different_hashes():
    """El hash de firma incluye el instante de la firma — no es un hash
    puramente del documento, sino de "este documento + este usuario + este
    momento"."""
    repository = _repository_with_available_signature()
    use_case = SignDocumentUseCase(repository)

    first = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=SIGNATURE_STEP.id,
        ip_address="203.0.113.7",
        user_agent=None,
    )

    # Reabrir el paso a mano para poder firmar una segunda vez en el test
    # (en producción esto no es posible: el paso ya está `completed`).
    from dataclasses import replace

    repository.progress[("user-1", SIGNATURE_STEP.id)] = replace(
        repository.progress[("user-1", SIGNATURE_STEP.id)], status="available"
    )

    second = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=SIGNATURE_STEP.id,
        ip_address="203.0.113.7",
        user_agent=None,
    )

    assert first.signature_hash != second.signature_hash


@pytest.mark.asyncio
async def test_rejects_signing_a_locked_step():
    repository = FakeOnboardingRepository(
        steps=ALL_STEPS, documents=[SIGNATURE_DOCUMENT]
    )
    repository.progress[("user-1", SIGNATURE_STEP.id)] = OnboardingProgress(
        id="progress-signature",
        user_id="user-1",
        step_id=SIGNATURE_STEP.id,
        status="locked",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = SignDocumentUseCase(repository)

    with pytest.raises(StepLockedError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            ip_address="203.0.113.7",
            user_agent=None,
        )


@pytest.mark.asyncio
async def test_rejects_when_no_active_document_configured():
    repository = _repository_with_available_signature(with_document=False)
    use_case = SignDocumentUseCase(repository)

    with pytest.raises(OnboardingDocumentNotFoundError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            ip_address="203.0.113.7",
            user_agent=None,
        )
