"""Resultados compuestos de casos de uso del feature `documents` que
necesitan devolver algo más que una entidad de dominio pura — mismo patrón
que `auth.application.results`."""

from dataclasses import dataclass

from ..domain.models import Document, SyncRun


@dataclass(frozen=True)
class DocumentDownload:
    """Resultado de `DownloadDocumentUseCase`: metadatos del documento
    (nombre/`mime_type` para el `Content-Disposition`, WU-C2) + el binario
    ya descargado desde el proveedor de almacenamiento activo."""

    document: Document
    content: bytes


@dataclass(frozen=True)
class BulkFolderProvisionResult:
    """Resumen de `BulkProvisionDriveFoldersUseCase` (batch de backfill,
    `POST /documents/provision-folders`): reusa la misma fila de
    `drive_sync_runs` que `SyncDocumentsUseCase` (auditoría), pero con
    conteos propios de "carpeta creada/omitida/fallida" — `SyncRun` en sí no
    modela ese desglose (`files_synced`/`error_detail` solo), así que este
    resultado los expone estructurados para la respuesta del endpoint."""

    sync_run: SyncRun
    created: int
    skipped: int
    failed: int
