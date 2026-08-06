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
from src.features.onboarding.domain.entities import (
    OnboardingDocument,
    OnboardingProgress,
)
from src.features.onboarding.domain.errors import (
    OnboardingDocumentNotFoundError,
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
        contract_type=None,
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
    # Tras la reordenación de v1.1 (`033_onboarding_steps_reorder_v11.sql`)
    # los manuales son el paso 3 y la documentación el 5, así que para llegar
    # aquí el manual TIENE que estar ya completado — al revés que antes, que
    # el manual (entonces el 4) nacía `locked` esperando a la firma (el 3).
    repository.progress[("user-1", MANUAL_STEP.id)] = OnboardingProgress(
        id="progress-manual",
        user_id="user-1",
        step_id=MANUAL_STEP.id,
        status="completed",
        progress_pct=100,
        data={},
        started_at=None,
        completed_at=datetime.now(timezone.utc),
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
async def test_happy_path_completes_the_step_and_closes_the_onboarding():
    """Este paso es EL ÚLTIMO desde la reordenación de v1.1, así que ya no
    "desbloquea el siguiente": no hay siguiente. Lo que comprueba este test es
    que se completa y que no reabre nada hacia atrás."""
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
    # El manual, que va DELANTE, sigue completado — `unlock_next_step` solo
    # mira hacia adelante y aquí no hay nada hacia adelante.
    assert progress_by_step[("user-1", MANUAL_STEP.id)].status == "completed"

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


# ─────────────────────────────────────────────────────────────────────────────
# Migración 046: el paso pasa de UN documento a CUATRO. La regla nueva es que el
# paso NO se cierra hasta que estén todos subidos — antes se cerraba con la
# primera subida porque no había más que uno.
# ─────────────────────────────────────────────────────────────────────────────


def _three_signature_documents() -> list[OnboardingDocument]:
    """Tres documentos activos con `display_order` distinto, como los cuatro que
    siembra la 046. Tres bastan para probar la regla y mantienen el test legible."""
    return [
        OnboardingDocument(
            id=f"doc-sig-{n}",
            kind="signature",
            title=f"Documento {n}",
            version=1,
            content_hash=f"{n}" * 64,
            storage_ref=f"generated:doc-{n}",
            is_active=True,
            display_order=n,
        )
        for n in (1, 2, 3)
    ]


def _repository_with_three_signature_documents() -> FakeOnboardingRepository:
    repository = _onboarding_repository_with_available_signature()
    repository.documents = {d.id: d for d in _three_signature_documents()}
    return repository


@pytest.mark.asyncio
async def test_step_stays_open_until_every_document_is_uploaded():
    """Con tres documentos, las dos primeras subidas registran su enlace pero
    dejan el paso ABIERTO. Antes de la 046 la primera lo cerraba, y con cuatro
    documentos eso habría dado el onboarding por terminado con tres sin firmar."""
    repository = _repository_with_three_signature_documents()
    use_case = _use_case(onboarding_repository=repository)

    for document_id in ("doc-sig-1", "doc-sig-2"):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="firmado.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
            document_id=document_id,
        )
        assert repository.progress[("user-1", SIGNATURE_STEP.id)].status == "available"

    assert len(repository.document_uploads) == 2


@pytest.mark.asyncio
async def test_step_completes_with_the_last_document():
    repository = _repository_with_three_signature_documents()
    use_case = _use_case(onboarding_repository=repository)

    for document_id in ("doc-sig-1", "doc-sig-2", "doc-sig-3"):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="firmado.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
            document_id=document_id,
        )

    assert repository.progress[("user-1", SIGNATURE_STEP.id)].status == "completed"


@pytest.mark.asyncio
async def test_documents_can_be_uploaded_in_any_order():
    """El paso 5 NO tiene cascada: la persona se descarga los cuatro, los firma
    de una sentada y los sube en el orden que quiera. Forzar el orden de los
    manuales aquí solo generaría rechazos que no protegen nada."""
    repository = _repository_with_three_signature_documents()
    use_case = _use_case(onboarding_repository=repository)

    for document_id in ("doc-sig-3", "doc-sig-1", "doc-sig-2"):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="firmado.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
            document_id=document_id,
        )

    assert repository.progress[("user-1", SIGNATURE_STEP.id)].status == "completed"


@pytest.mark.asyncio
async def test_missing_document_id_is_rejected_when_there_are_several():
    """Adivinar sería peor que fallar: apuntar el consentimiento de imágenes
    como si fuera el RGPD deja el paso cerrado con documentos cruzados y sin
    forma de detectarlo."""
    repository = _repository_with_three_signature_documents()
    use_case = _use_case(onboarding_repository=repository)

    with pytest.raises(OnboardingDocumentNotFoundError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="firmado.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
        )

    assert repository.document_uploads == []


@pytest.mark.asyncio
async def test_missing_document_id_still_works_with_a_single_document():
    """Compatibilidad con el cliente anterior a la 046, que subía sin id: con un
    único documento activo sigue siendo inequívoco."""
    repository = _onboarding_repository_with_available_signature()
    use_case = _use_case(onboarding_repository=repository)

    upload = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=SIGNATURE_STEP.id,
        filename="firmado.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    assert upload.onboarding_document_id == SIGNATURE_DOCUMENT.id


@pytest.mark.asyncio
async def test_document_id_from_another_step_is_rejected():
    """Un id que no está entre los `signature` activos no es subible, aunque sea
    un UUID válido — mismo criterio que la cascada de manuales."""
    repository = _repository_with_three_signature_documents()
    use_case = _use_case(onboarding_repository=repository)

    with pytest.raises(OnboardingDocumentNotFoundError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="firmado.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
            document_id="doc-manual-hincator",
        )


# ─────────────────────────────────────────────────────────────────────────────
# El nombre del fichero EN DRIVE. `UploadDocumentUseCase` usa el `filename` que
# se le pasa como nombre real en `{email}/Firmados/`, y con cuatro documentos el
# nombre que trae el navegador deja la carpeta ilegible para RRHH.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drive_filename_comes_from_the_document_not_from_the_browser():
    """Los cuatro escaneos pueden llegar llamándose igual (`scan.pdf`): es lo que
    hace un móvil o un escáner de oficina. Drive NO sobrescribe nombres repetidos,
    los admite, así que sin esto la carpeta `Firmados` acaba con cuatro PDF
    indistinguibles y RRHH no sabe cuál es cuál."""
    storage = FakeDocumentStorage()
    upload_document = UploadDocumentUseCase(
        FakeDocumentRepository(), storage, FakeStaffRepository([_staff_member()]), 10
    )
    repository = _repository_with_three_signature_documents()
    use_case = _use_case(
        onboarding_repository=repository, upload_document_use_case=upload_document
    )

    for document_id in ("doc-sig-1", "doc-sig-2", "doc-sig-3"):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=SIGNATURE_STEP.id,
            filename="scan.pdf",  # el mismo nombre en las tres subidas
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
            document_id=document_id,
        )

    nombres = [call["filename"] for call in storage.upload_calls]
    assert nombres == ["Documento 1.pdf", "Documento 2.pdf", "Documento 3.pdf"]
    # Lo que de verdad importa: en Drive son distinguibles entre sí.
    assert len(set(nombres)) == 3
    assert "scan.pdf" not in nombres


@pytest.mark.asyncio
async def test_drive_filename_sanitises_slashes_from_the_title():
    """Una barra en el título no debe llegar al nombre del fichero: en Drive no
    crea jerarquía, pero se muestra escapada y confunde."""
    storage = FakeDocumentStorage()
    upload_document = UploadDocumentUseCase(
        FakeDocumentRepository(), storage, FakeStaffRepository([_staff_member()]), 10
    )
    repository = _onboarding_repository_with_available_signature()
    repository.documents = {
        "doc-barra": OnboardingDocument(
            id="doc-barra",
            kind="signature",
            title="RGPD / LOPDGDD",
            version=1,
            content_hash="ab" * 32,
            storage_ref="generated:rgpd-informacion",
            is_active=True,
        )
    }
    use_case = _use_case(
        onboarding_repository=repository, upload_document_use_case=upload_document
    )

    await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=SIGNATURE_STEP.id,
        filename="scan.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
        document_id="doc-barra",
    )

    assert storage.upload_calls[0]["filename"] == "RGPD - LOPDGDD.pdf"


@pytest.mark.asyncio
async def test_signed_documents_land_in_the_signed_category():
    """`category='signed'` es lo que los manda a la subcarpeta «Firmados» de Drive
    (`CATEGORY_FOLDER_NAMES`), separados de nóminas y contratos."""
    storage = FakeDocumentStorage()
    document_repository = FakeDocumentRepository()
    upload_document = UploadDocumentUseCase(
        document_repository, storage, FakeStaffRepository([_staff_member()]), 10
    )
    use_case = _use_case(upload_document_use_case=upload_document)

    await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=SIGNATURE_STEP.id,
        filename="scan.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    assert storage.category_folders
    categorias = [c for cats in storage.category_folders.values() for c in cats]
    assert categorias == ["signed"]
