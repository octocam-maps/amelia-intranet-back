"""Resultados compuestos de casos de uso del feature `documents` que
necesitan devolver algo más que una entidad de dominio pura — mismo patrón
que `auth.application.results`."""

from dataclasses import dataclass
from typing import Optional

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


@dataclass(frozen=True)
class FolderPlanEntry:
    """Qué haría el provisioning con UNA persona, sin hacerlo.

    `action` es el veredicto:
      - `ya_registrada`   -> tiene `drive_folder_id` cacheado; ni se consulta a Drive
      - `ya_en_su_sitio`  -> la carpeta existe bajo su entidad; solo se cachearía el id
      - `mover`           -> existe SUELTA en la raíz (árbol plano) y se movería
      - `crear`           -> no existe en ninguna parte
    """

    user_id: str
    email: str
    entity_name: Optional[str]
    action: str
    missing_categories: list[str]


@dataclass(frozen=True)
class BulkFolderPlan:
    """Resultado de la pasada EN SECO. No escribe nada en Drive ni deja fila
    en `drive_sync_runs`: es una fotografía de lo que ocurriría.

    `entity_folders_to_create` son las carpetas de sociedad que hoy no
    existen. Van aparte porque se comparten entre personas: contarlas por
    empleado multiplicaría por 40 lo que son 4 carpetas.
    """

    entries: list[FolderPlanEntry]
    entity_folders_to_create: list[str]

    @property
    def to_create(self) -> int:
        return sum(1 for e in self.entries if e.action == "crear")

    @property
    def to_move(self) -> int:
        return sum(1 for e in self.entries if e.action == "mover")

    @property
    def already_ok(self) -> int:
        return sum(1 for e in self.entries if e.action in ("ya_registrada", "ya_en_su_sitio"))

    @property
    def category_folders_to_create(self) -> int:
        return sum(len(e.missing_categories) for e in self.entries)

    @property
    def estimated_drive_writes(self) -> int:
        """Escrituras que costaría aplicarlo. Drive limita por proyecto y por
        usuario: saber el número ANTES evita descubrir el `rateLimitExceeded`
        a mitad del batch."""
        return (
            len(self.entity_folders_to_create)
            + self.to_create
            + self.to_move
            + self.category_folders_to_create
        )
