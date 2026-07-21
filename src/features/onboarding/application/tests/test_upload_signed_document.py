"""
Tests de `UploadSignedOnboardingDocumentUseCase` (sdd/docs-firmados-upload-drive,
D2): reemplaza a la firma nativa (`SignDocumentUseCase`, eliminado) — el paso
3 se completa subiendo el PDF ya firmado fuera de la plataforma, delegando
en `UploadDocumentUseCase` COMPLETO (categoría/MIME/tamaño, Drive,
`employee_documents`, notificación) y añadiendo solo el enlace propio de
onboarding (`onboarding_document_uploads`, D3).

Se usa un `UploadDocumentUseCase` REAL (con los fakes de `documents`, no un
doble de onboarding) porque lo que se prueba es precisamente la composición
entre ambos casos de uso (D1) — un fake más fino no detectaría una
regresión en cómo se pasan los parámetros de un lado a otro.
"""

from datetime import datetime, timezone

import pytest

from src.features.documents.application.errors import (
    DocumentTooLargeError,
    InvalidDocumentMimeTypeError,
)
from src.features.documents.application.tests.fakes import (
    FakeDocumentRepository,
    FakeDocumentStorage,
    FakeStaffRepository,
)
from src.features.documents.application.use_cases.upload_document import UploadDocumentUseCase
from src.features.onboarding.domain.entities import OnboardingProgress
from src.features.onboarding.domain.errors import (
    StepLockedError,
    StepNotAvailableForRoleError,
    StepNotOperableError,
)
from src.features.staff.domain.entities import StaffMember

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_STEP, SIGNATURE_DOCUMENT, SIGNATURE_STEP

from src.features.onboarding.application.use_cases.upload_signed_document import (
    UploadSignedOnboardingDocumentUseCase,
)


def _staff_member(**overrides) -> StaffMember:
    defaults = dict(
        id="user-1",
        full_name="Ana García",
        email="ana.garcia@ameliahub.com",
        avatar_url=None,
        job_title=None,
        department_id=None,
        department_name=None,
        entity_id=None,
        entity_code=None,
        role_id="role-empleado",
        role_code="empleado",
        status="active",
        hire_date=None,
        vacation_days_per_year=None,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return StaffMember(**defaults)


def _upload_document_use_case(*, max_upload_mb: int = 10) -> UploadDocumentUseCase:
    return UploadDocumentUseCase(
        FakeDocumentRepository(),
        FakeDocumentStorage(),
        FakeStaffRepository([_staff_member()]),
        max_upload_mb,
    )


def _onboarding_repository_with_available_signature(
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
    # El paso 4 (manual) nace `locked` en un onboarding real hasta que se
    # completa el 3 — necesario para comprobar que se desbloquea.
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
    return repository


def _use_case(
    *, onboarding_repository=None, upload_document_use_case=None
) -> UploadSignedOnboardingDocumentUseCase:
    return UploadSignedOnboardingDocumentUseCase(
        onboarding_repository or _onboarding_repository_with_available_signature(),
        upload_document_use_case or _upload_document_use_case(),
    )


@pytest.mark.asyncio
async def test_happy_path_completes_the_step_and_unlocks_the_next_one():
    onboarding_repository = _onboarding_repository_with_available_signature()
    use_case = _use_case(onboarding_repository=onboarding_repository)

    upload = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=SIGNATURE_STEP.id,
        filename="documentacion-firmada.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    assert upload.user_id == "user-1"
    assert upload.onboarding_document_id == SIGNATURE_DOCUMENT.id
    assert upload.employee_document_id is not None

    progress_by_step = onboarding_repository.progress
    assert progress_by_step[("user-1", SIGNATURE_STEP.id)].status == "completed"
    assert progress_by_step[("user-1", MANUAL_STEP.id)].status == "available"

    # El enlace de onboarding queda registrado (D3) además del
    # `employee_documents` que ya crea `UploadDocumentUseCase`.
    assert len(onboarding_repository.document_uploads) == 1
    assert onboarding_repository.document_uploads[0].employee_document_id == upload.employee_document_id


@pytest.mark.asyncio
async def test_rejects_when_the_step_is_already_completed():
    onboarding_repository = _onboarding_repository_with_available_signature()
    onboarding_repository.progress[("user-1", SIGNATURE_STEP.id)] = OnboardingProgress(
        id="progress-signature",
        user_id="user-1",
        step_id=SIGNATURE_STEP.id,
        status="completed",
        progress_pct=100,
        data={"employee_document_id": "employee-doc-old"},
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    use_case = _use_case(onboarding_repository=onboarding_repository)

    with pytest.raises(StepNotOperableError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="documentacion-firmada.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_rejects_when_the_step_is_locked_by_sequence():
    onboarding_repository = _onboarding_repository_with_available_signature()
    onboarding_repository.progress[("user-1", SIGNATURE_STEP.id)] = OnboardingProgress(
        id="progress-signature",
        user_id="user-1",
        step_id=SIGNATURE_STEP.id,
        status="locked",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = _use_case(onboarding_repository=onboarding_repository)

    with pytest.raises(StepLockedError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="documentacion-firmada.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_rejects_a_disallowed_mime_type_and_does_not_complete_the_step():
    onboarding_repository = _onboarding_repository_with_available_signature()
    use_case = _use_case(onboarding_repository=onboarding_repository)

    with pytest.raises(InvalidDocumentMimeTypeError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="documentacion-firmada.docx",
            content=b"contenido",
            mime_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )

    assert onboarding_repository.progress[("user-1", SIGNATURE_STEP.id)].status == "available"
    assert onboarding_repository.document_uploads == []


@pytest.mark.asyncio
async def test_rejects_a_file_over_the_max_upload_size_and_does_not_complete_the_step():
    onboarding_repository = _onboarding_repository_with_available_signature()
    use_case = _use_case(
        onboarding_repository=onboarding_repository,
        upload_document_use_case=_upload_document_use_case(max_upload_mb=1),
    )

    with pytest.raises(DocumentTooLargeError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="documentacion-firmada.pdf",
            content=b"0" * (2 * 1024 * 1024),
            mime_type="application/pdf",
        )

    assert onboarding_repository.progress[("user-1", SIGNATURE_STEP.id)].status == "available"
    assert onboarding_repository.document_uploads == []


@pytest.mark.asyncio
async def test_externo_invitado_cannot_operate_the_step_even_invoking_it_directly():
    """Defensa en profundidad (docs/permisos-roles.md: onboarding parcial,
    sin documento firmado) — se rechaza en el USE CASE, no solo en el
    `require_role` del router."""
    onboarding_repository = _onboarding_repository_with_available_signature()
    use_case = _use_case(onboarding_repository=onboarding_repository)

    with pytest.raises(StepNotAvailableForRoleError):
        await use_case.execute(
            user_id="guest-1",
            role="externo_invitado",
            step_id=SIGNATURE_STEP.id,
            filename="documentacion-firmada.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
        )
