"""Cableado de los disparadores `payslip_available`/`document_uploaded` en
`UploadDocumentUseCase` (RF §6): una nómina notifica `payslip_available`,
cualquier otra categoría notifica `document_uploaded` — siempre al DUEÑO del
documento (`user_id`), nunca a quien lo subió (`uploaded_by`).
`NotifyUseCase.execute` en sí ya tiene su propia suite en
`features/notifications`; aquí solo se verifica que el use case la invoca
con el tipo/destinatario correctos."""

from datetime import datetime, timezone

import pytest

from src.features.documents.application.tests.fakes import (
    FakeDocumentRepository,
    FakeDocumentStorage,
    FakeStaffRepository,
)
from src.features.documents.application.use_cases.upload_document import UploadDocumentUseCase
from src.features.staff.domain.entities import StaffMember


class _RecordingNotify:
    def __init__(self):
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)


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


def _use_case(*, notify=None, max_upload_mb=10):
    repository = FakeDocumentRepository()
    storage = FakeDocumentStorage()
    staff_repository = FakeStaffRepository([_staff_member()])
    use_case = UploadDocumentUseCase(
        repository, storage, staff_repository, max_upload_mb, notify
    )
    return use_case


@pytest.mark.asyncio
async def test_uploading_a_payslip_notifies_payslip_available():
    notify = _RecordingNotify()
    use_case = _use_case(notify=notify)

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

    assert len(notify.calls) == 1
    assert notify.calls[0]["type"] == "payslip_available"
    assert notify.calls[0]["recipient_ids"] == ["user-1"]


@pytest.mark.parametrize("category", ["contract", "general", "other", "signed"])
@pytest.mark.asyncio
async def test_uploading_a_non_payslip_notifies_document_uploaded(category):
    """`signed` (sdd/docs-firmados-upload-drive): el documento firmado que
    sube el propio empleado en el paso 3 cae en la misma rama que
    contract/general/other — `notify_document_created` solo distingue
    `payslip` como caso especial (T0.3, confirmado en el propio código)."""
    notify = _RecordingNotify()
    use_case = _use_case(notify=notify)

    await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-1",
        category=category,
        title="Documento",
        period=None,
        filename="doc.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    assert len(notify.calls) == 1
    assert notify.calls[0]["type"] == "document_uploaded"
    assert notify.calls[0]["recipient_ids"] == ["user-1"]


@pytest.mark.asyncio
async def test_notifies_the_document_owner_not_whoever_uploaded_it():
    notify = _RecordingNotify()
    use_case = _use_case(notify=notify)

    await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-99",
        category="general",
        title="Documento",
        period=None,
        filename="doc.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    assert notify.calls[0]["recipient_ids"] == ["user-1"]
    assert "admin-99" not in notify.calls[0]["recipient_ids"]


@pytest.mark.asyncio
async def test_upload_without_a_notify_dependency_still_works():
    use_case = _use_case(notify=None)

    document = await use_case.execute(
        user_id="user-1",
        uploaded_by="admin-1",
        category="general",
        title="Documento",
        period=None,
        filename="doc.pdf",
        content=b"%PDF-1.4 contenido",
        mime_type="application/pdf",
    )

    assert document.category == "general"
