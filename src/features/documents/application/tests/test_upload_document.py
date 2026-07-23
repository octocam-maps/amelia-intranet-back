"""Tests de `UploadDocumentUseCase` — validación de MIME/tamaño, resolución
(y caché) de la subcarpeta de Drive del empleado, y creación de la fila de
metadatos."""

from datetime import datetime, timezone

import pytest

from src.features.documents.application.errors import (
    DocumentOwnerNotFoundError,
    DocumentTooLargeError,
    InvalidDocumentCategoryError,
    InvalidDocumentMimeTypeError,
)
from src.features.documents.application.tests.fakes import (
    FakeDocumentRepository,
    FakeDocumentStorage,
    FakeStaffRepository,
)
from src.features.documents.application.use_cases.upload_document import UploadDocumentUseCase
from src.features.staff.domain.entities import StaffMember


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


def _use_case(*, repository=None, storage=None, staff_repository=None, max_upload_mb=10):
    repository = repository or FakeDocumentRepository()
    storage = storage or FakeDocumentStorage()
    staff_repository = staff_repository or FakeStaffRepository([_staff_member()])
    use_case = UploadDocumentUseCase(repository, storage, staff_repository, max_upload_mb)
    return use_case, repository, storage, staff_repository


@pytest.mark.asyncio
async def test_uploads_document_and_persists_metadata():
    use_case, _, storage, _ = _use_case()

    document = await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-1",
        category="payslip",
        title="Nómina julio 2026",
        period="2026-07",
        filename="nomina-2026-07.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    assert document.user_id == "user-1"
    assert document.category == "payslip"
    assert document.uploaded_by == "admin-1"
    assert document.drive_file_id is not None
    assert len(storage.upload_calls) == 1


@pytest.mark.asyncio
async def test_caches_drive_folder_id_across_uploads():
    use_case, repository, storage, _ = _use_case()

    await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-1",
        category="payslip",
        title="Nómina julio 2026",
        period="2026-07",
        filename="nomina-2026-07.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )
    await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-1",
        category="contract",
        title="Contrato",
        period=None,
        filename="contrato.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    # La subcarpeta se resuelve/crea UNA sola vez: la segunda subida ya la
    # encuentra cacheada en `users.drive_folder_id` (repo fake).
    assert len(storage.folders_by_email) == 1
    assert await repository.find_drive_folder_id("user-1") is not None


@pytest.mark.asyncio
async def test_uploads_to_the_category_subfolder_not_to_the_employee_root():
    use_case, repository, storage, _ = _use_case()

    await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-1",
        category="payslip",
        title="Nómina julio 2026",
        period="2026-07",
        filename="nomina-2026-07.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    employee_folder_id = await repository.find_drive_folder_id("user-1")
    uploaded_to_folder_id = storage.upload_calls[0]["folder_id"]
    assert uploaded_to_folder_id != employee_folder_id
    assert uploaded_to_folder_id == await storage.find_category_folder(
        employee_folder_id, "payslip"
    )


@pytest.mark.asyncio
async def test_different_categories_of_the_same_employee_use_different_subfolders():
    use_case, _, storage, _ = _use_case()

    await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-1",
        category="payslip",
        title="Nómina julio 2026",
        period="2026-07",
        filename="nomina-2026-07.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )
    await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-1",
        category="contract",
        title="Contrato",
        period=None,
        filename="contrato.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    payslip_folder_id, contract_folder_id = (
        call["folder_id"] for call in storage.upload_calls
    )
    assert payslip_folder_id != contract_folder_id


@pytest.mark.asyncio
async def test_rejects_pdf_with_a_spoofed_content_type_header():
    """LOGIC-1: `content_type` es un header multipart que controla el
    cliente — declarar `application/pdf` no basta si el CONTENIDO real no es
    un PDF (magic bytes `%PDF-`). Sin esta validación, se puede subir
    cualquier basura y marcar el paso 3 de firma del onboarding como
    completado."""
    use_case, _, storage, _ = _use_case()

    with pytest.raises(InvalidDocumentMimeTypeError):
        await use_case.execute(
            user_id="user-1",
            uploaded_by="user-1",
            category="signed",
            title="Documentación laboral",
            period=None,
            filename="falso.pdf",
            content=b"esto no es un PDF, solo texto plano",
            mime_type="application/pdf",
        )

    assert storage.upload_calls == []


@pytest.mark.asyncio
async def test_rejects_non_pdf_mime_type():
    use_case, *_ = _use_case()

    with pytest.raises(InvalidDocumentMimeTypeError):
        await use_case.execute(
            user_id="user-1",
            uploaded_by="admin-1",
            category="general",
            title="Foto",
            period=None,
            filename="foto.png",
            content=b"contenido",
            mime_type="image/png",
        )


@pytest.mark.asyncio
async def test_rejects_file_over_max_upload_size():
    use_case, *_ = _use_case(max_upload_mb=1)

    with pytest.raises(DocumentTooLargeError):
        await use_case.execute(
            user_id="user-1",
            uploaded_by="admin-1",
            category="general",
            title="Archivo grande",
            period=None,
            filename="grande.pdf",
            content=b"0" * (2 * 1024 * 1024),
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_accepts_signed_category():
    """`signed` (sdd/docs-firmados-upload-drive): documento firmado subido
    por el propio empleado en el paso 3 del onboarding — se indexa como un
    documento más, misma validación que el resto de categorías."""
    use_case, _, storage, _ = _use_case()

    document = await use_case.execute(
        user_id="user-1",
        uploaded_by="user-1",
        category="signed",
        title="Documentación laboral",
        period=None,
        filename="firmado.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    assert document.category == "signed"
    assert len(storage.upload_calls) == 1


@pytest.mark.asyncio
async def test_rejects_invalid_category():
    use_case, *_ = _use_case()

    with pytest.raises(InvalidDocumentCategoryError):
        await use_case.execute(
            user_id="user-1",
            uploaded_by="admin-1",
            category="invalid",
            title="Documento",
            period=None,
            filename="doc.pdf",
            content=b"contenido",
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_rejects_unknown_user_id():
    use_case, *_ = _use_case(staff_repository=FakeStaffRepository())

    with pytest.raises(DocumentOwnerNotFoundError):
        await use_case.execute(
            user_id="user-inexistente",
            uploaded_by="admin-1",
            category="general",
            title="Documento",
            period=None,
            filename="doc.pdf",
            content=b"%PDF-1.4 contenido",
            mime_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_validates_mime_before_touching_storage():
    # Fail-fast: MIME/tamaño/categoría se validan ANTES de tocar el storage
    # o el repositorio de plantilla — evita subir a Drive un archivo que se
    # va a rechazar igual.
    use_case, _, storage, _ = _use_case(staff_repository=FakeStaffRepository())

    with pytest.raises(InvalidDocumentMimeTypeError):
        await use_case.execute(
            user_id="user-inexistente",
            uploaded_by="admin-1",
            category="general",
            title="Documento",
            period=None,
            filename="doc.png",
            content=b"contenido",
            mime_type="image/png",
        )

    assert storage.upload_calls == []
