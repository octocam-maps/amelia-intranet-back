"""
Entidades y value objects de dominio del feature `documents`. Sin
dependencias de framework/SQL — el binario del documento vive en Google
Drive (puerto `IDocumentStorage`), Postgres (`employee_documents`) solo
indexa los metadatos. Ver `sdd/fase4-nominas-documentos/design` para el
enfoque completo (Drive real desde v1, no BYTEA).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Valores permitidos de `employee_documents.category` (CHECK en
# `004_documents.sql`). El proyecto no usa `Enum` de Python en el dominio
# (ver `absences.AbsenceType.code`, `staff`, etc.) — el mismo criterio aquí:
# strings validados contra esta lista donde haga falta (WU-C1,
# `UploadDocumentUseCase`) + el CHECK de la base de datos como cinturón de
# seguridad final.
DOCUMENT_CATEGORIES = frozenset({"payslip", "contract", "general", "other"})

# Nombre EXACTO (con acento) de la subcarpeta de Drive por categoría, dentro
# de la carpeta del empleado (`<email>/<subcarpeta>/...`) — decisión del
# usuario para organizar Fase 4: cada categoría vive en su propia subcarpeta
# en vez de caer todas juntas en la raíz del empleado. Usado tanto para
# resolver/crear la subcarpeta al subir (`get_or_create_category_folder`)
# como para resolverla al conciliar en el sync (`find_category_folder`,
# `IDocumentStorage`) — el sync itera las categorías conocidas y le pide a
# cada una su subcarpeta, no al revés (no necesita mapear nombre->categoría).
CATEGORY_FOLDER_NAMES: dict[str, str] = {
    "payslip": "Nóminas",
    "contract": "Contratos",
    "general": "General",
    "other": "Otros",
}


@dataclass(frozen=True)
class Document:
    """Una fila de `employee_documents`. RGPD: el filtrado por `user_id`
    (dueño) ocurre siempre en el repositorio (WU-C1), nunca solo en la UI."""

    id: str
    user_id: str
    category: str
    title: str
    period: Optional[str]  # 'YYYY-MM' para nóminas; None en el resto
    drive_file_id: Optional[str]
    mime_type: str
    content_hash: Optional[str]
    uploaded_by: Optional[str]  # None = insertado por el sync automático (WU-D)
    uploaded_at: datetime
    created_at: datetime
    deleted_at: Optional[datetime] = None


@dataclass(frozen=True)
class SyncRun:
    """Una fila de `drive_sync_runs` — auditoría del volcado automático
    (WU-D). Se modela ya en esta work-unit porque `IDocumentRepository`
    declara sus operaciones aquí, aunque la implementación llegue después."""

    id: str
    started_at: datetime
    finished_at: Optional[datetime]
    status: str  # 'running' | 'success' | 'partial' | 'failed'
    files_synced: int
    error_detail: Optional[str]


@dataclass(frozen=True)
class UploadedFile:
    """Resultado de `IDocumentStorage.upload` — lo mínimo que necesita el
    use case (WU-C1) para persistir la fila de `employee_documents`."""

    drive_file_id: str
    content_hash: str  # md5Checksum que devuelve Drive (decisión de diseño)


@dataclass(frozen=True)
class DriveFileMetadata:
    """Una fila cruda de `IDocumentStorage.list_folder_files` — insumo del
    sync (WU-D). El filtro de negocio (mimeType=application/pdf, tamaño
    ≤ DOCUMENTS_MAX_UPLOAD_MB) vive en el use case, NO en el puerto."""

    drive_file_id: str
    name: str
    mime_type: str
    size_bytes: int
    content_hash: str
