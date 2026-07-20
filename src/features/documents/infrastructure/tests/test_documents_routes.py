"""Test route-level de `/documents`: el externo-invitado NO tiene
"Documentos"/"Nóminas" en la matriz de permisos (docs/permisos-roles.md: ❌)
— debe rechazarse en el BACKEND, no solo ocultarse del navbar. RGPD: un
empleado/socio solo accede a lo suyo. Mismo patrón que
`features/absences/infrastructure/tests/test_absences_routes.py`."""

import io
import os
from datetime import datetime, timezone
from typing import Optional

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.documents.application.errors import (  # noqa: E402
    DocumentForbiddenError,
    DocumentNotFoundError,
    DocumentTooLargeError,
    InvalidDocumentMimeTypeError,
)
from src.features.documents.domain.models import Document, SyncRun  # noqa: E402
from src.features.documents.domain.ports import DriveFileNotFoundError  # noqa: E402
from src.features.documents.infrastructure import dependencies as documents_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {
            "sub": "user-1",
            "email": "user@ameliahub.com",
            "role": role,
            "entity_id": None,
            "is_external": role == "externo_invitado",
        }
    )


def _document(**overrides) -> Document:
    now = datetime.now(timezone.utc)
    kwargs = dict(
        id="doc-1",
        user_id="user-1",
        category="payslip",
        title="Nómina julio 2026",
        period="2026-07",
        drive_file_id="drive-1",
        mime_type="application/pdf",
        content_hash="hash-1",
        uploaded_by="admin-1",
        uploaded_at=now,
        created_at=now,
        deleted_at=None,
    )
    kwargs.update(overrides)
    return Document(**kwargs)


# --- RBAC: externo-invitado excluido de los 4 endpoints. ---


def test_externo_invitado_cannot_list_documents():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents", headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_upload_document():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents",
                data={"user_id": "user-1", "category": "payslip", "title": "Nómina"},
                files={"file": ("nomina.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_download_document():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents/doc-1/download",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_delete_document():
    try:
        with TestClient(app) as client:
            response = client.delete(
                "/documents/doc-1",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


# --- RBAC: subida/borrado son exclusivos del admin. ---


def test_empleado_cannot_upload_document():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents",
                data={"user_id": "user-1", "category": "payslip", "title": "Nómina"},
                files={"file": ("nomina.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_socio_cannot_delete_document():
    try:
        with TestClient(app) as client:
            response = client.delete(
                "/documents/doc-1", headers={"Authorization": f"Bearer {_token_for('socio')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


# --- GET /documents — listado con alcance RGPD. ---


class _FakeListDocumentsUseCase:
    def __init__(self, documents: Optional[list[Document]] = None, error: Optional[Exception] = None):
        self._documents = documents if documents is not None else [_document()]
        self._error = error

    async def execute(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._documents


def test_empleado_can_list_own_documents():
    app.dependency_overrides[documents_dependencies.get_list_documents_use_case] = (
        lambda: _FakeListDocumentsUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["documents"][0]["id"] == "doc-1"
    assert body["documents"][0]["category"] == "payslip"
    # `drive_file_id`/`content_hash` son detalles internos del proveedor —
    # nunca se exponen en el DTO.
    assert "drive_file_id" not in body["documents"][0]
    assert "content_hash" not in body["documents"][0]


def test_empleado_cannot_list_documents_of_another_user():
    """RGPD: pedir `user_id` de otro se rechaza en el backend
    (`ListDocumentsUseCase`), aunque el frontend nunca lo pida por su cuenta."""
    app.dependency_overrides[documents_dependencies.get_list_documents_use_case] = (
        lambda: _FakeListDocumentsUseCase(
            error=DocumentForbiddenError("No puedes ver los documentos de otro usuario.")
        )
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents?user_id=user-2",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_socio_can_list_own_documents():
    """`socio` [migración 024] = igual que empleado en todo lo relativo a
    sus propios documentos."""
    app.dependency_overrides[documents_dependencies.get_list_documents_use_case] = (
        lambda: _FakeListDocumentsUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents", headers={"Authorization": f"Bearer {_token_for('socio')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["documents"]) == 1


def test_admin_can_list_documents_of_any_user():
    app.dependency_overrides[documents_dependencies.get_list_documents_use_case] = (
        lambda: _FakeListDocumentsUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents?user_id=user-2&category=payslip",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["documents"]) == 1


# --- POST /documents — subida (admin). ---


class _FakeUploadDocumentUseCase:
    def __init__(self, document: Optional[Document] = None, error: Optional[Exception] = None):
        self._document = document if document is not None else _document()
        self._error = error
        self.received_kwargs: Optional[dict] = None

    async def execute(self, **kwargs):
        self.received_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._document


def test_admin_can_upload_document():
    fake_use_case = _FakeUploadDocumentUseCase()
    app.dependency_overrides[documents_dependencies.get_upload_document_use_case] = (
        lambda: fake_use_case
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents",
                data={
                    "user_id": "user-1",
                    "category": "payslip",
                    "title": "Nómina julio 2026",
                    "period": "2026-07",
                },
                files={"file": ("nomina.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == "doc-1"
    # El binario leído del `UploadFile` llega al caso de uso como `bytes`,
    # junto con el `uploaded_by` resuelto del JWT (nunca del body).
    assert fake_use_case.received_kwargs["content"] == b"%PDF-1.4"
    assert fake_use_case.received_kwargs["uploaded_by"] == "user-1"
    assert fake_use_case.received_kwargs["mime_type"] == "application/pdf"


def test_upload_rejects_non_pdf_file():
    app.dependency_overrides[documents_dependencies.get_upload_document_use_case] = (
        lambda: _FakeUploadDocumentUseCase(
            error=InvalidDocumentMimeTypeError("Solo se admiten documentos 'application/pdf'.")
        )
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents",
                data={"user_id": "user-1", "category": "payslip", "title": "Nómina"},
                files={"file": ("nomina.docx", io.BytesIO(b"no-pdf"), "application/msword")},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_upload_rejects_file_over_size_limit():
    app.dependency_overrides[documents_dependencies.get_upload_document_use_case] = (
        lambda: _FakeUploadDocumentUseCase(
            error=DocumentTooLargeError("El archivo supera el límite de 10 MB.")
        )
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents",
                data={"user_id": "user-1", "category": "payslip", "title": "Nómina"},
                files={"file": ("nomina.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# --- GET /documents/{id}/download — alcance RGPD + traducción de errores. ---


class _FakeDownloadDocumentUseCase:
    def __init__(self, download=None, error: Optional[Exception] = None):
        self._download = download
        self._error = error

    async def execute(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._download


def test_empleado_can_download_own_document():
    from src.features.documents.application.results import DocumentDownload

    download = DocumentDownload(document=_document(), content=b"%PDF-1.4")
    app.dependency_overrides[documents_dependencies.get_download_document_use_case] = (
        lambda: _FakeDownloadDocumentUseCase(download=download)
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents/doc-1/download",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    content_disposition = response.headers["content-disposition"]
    # `filename` es el fallback ASCII (sin tilde); `filename*` (RFC 6266)
    # lleva el nombre real codificado — ver `routes.py::download_document`.
    assert 'filename="Nmina julio 2026.pdf"' in content_disposition
    assert "filename*=UTF-8''N%C3%B3mina%20julio%202026.pdf" in content_disposition
    assert response.content == b"%PDF-1.4"


def test_empleado_cannot_download_document_of_another_user():
    app.dependency_overrides[documents_dependencies.get_download_document_use_case] = (
        lambda: _FakeDownloadDocumentUseCase(
            error=DocumentForbiddenError("No puedes descargar el documento de otro usuario.")
        )
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents/doc-2/download",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_download_returns_404_when_metadata_missing():
    app.dependency_overrides[documents_dependencies.get_download_document_use_case] = (
        lambda: _FakeDownloadDocumentUseCase(
            error=DocumentNotFoundError("No existe el documento id='doc-999'.")
        )
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents/doc-999/download",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_download_returns_404_when_drive_file_missing():
    """`DriveFileNotFoundError` no es un `BaseError` (vive en `domain.ports`)
    — la ruta debe traducirlo al mismo 404 que `DocumentNotFoundError`."""
    app.dependency_overrides[documents_dependencies.get_download_document_use_case] = (
        lambda: _FakeDownloadDocumentUseCase(error=DriveFileNotFoundError())
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/documents/doc-1/download",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


# --- DELETE /documents/{id} — borrado (admin). ---


class _FakeDeleteDocumentUseCase:
    def __init__(self, error: Optional[Exception] = None):
        self._error = error

    async def execute(self, **kwargs):
        if self._error is not None:
            raise self._error


def test_admin_can_delete_document():
    app.dependency_overrides[documents_dependencies.get_delete_document_use_case] = (
        lambda: _FakeDeleteDocumentUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.delete(
                "/documents/doc-1",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204


# --- POST /documents/sync — conciliación Drive -> Postgres (admin, WU-D). ---


class _FakeSyncDocumentsUseCase:
    def __init__(self, sync_run=None, error: Optional[Exception] = None):
        self._sync_run = sync_run or SyncRun(
            id="sync-run-1",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            status="success",
            files_synced=3,
            error_detail=None,
        )
        self._error = error

    async def execute(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._sync_run


def test_admin_can_trigger_sync():
    app.dependency_overrides[documents_dependencies.get_sync_documents_use_case] = (
        lambda: _FakeSyncDocumentsUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents/sync",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "sync-run-1"
    assert body["status"] == "success"
    assert body["files_synced"] == 3


def test_empleado_cannot_trigger_sync():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents/sync",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_socio_cannot_trigger_sync():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents/sync",
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_trigger_sync():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents/sync",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_delete_returns_404_when_not_found():
    app.dependency_overrides[documents_dependencies.get_delete_document_use_case] = (
        lambda: _FakeDeleteDocumentUseCase(
            error=DocumentNotFoundError("No existe el documento id='doc-999'.")
        )
    )
    try:
        with TestClient(app) as client:
            response = client.delete(
                "/documents/doc-999",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
