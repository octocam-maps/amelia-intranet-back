"""Resultados compuestos de casos de uso del feature `documents` que
necesitan devolver algo más que una entidad de dominio pura — mismo patrón
que `auth.application.results`."""

from dataclasses import dataclass
from typing import Optional

from ..domain.models import CATEGORY_FOLDER_NAMES, Document

CATEGORY_FOLDER_COUNT = len(CATEGORY_FOLDER_NAMES)


@dataclass(frozen=True)
class DocumentDownload:
    """Resultado de `DownloadDocumentUseCase`: metadatos del documento
    (nombre/`mime_type` para el `Content-Disposition`, WU-C2) + el binario
    ya descargado desde el proveedor de almacenamiento activo."""

    document: Document
    content: bytes


@dataclass(frozen=True)
class FolderBatchResult:
    """Resultado de UN lote del volcado (`POST /documents/provision-folders`).

    No hay fila de `drive_sync_runs`: ese reuso nunca encajó —`files_synced` no
    significa nada al crear carpetas, y por eso hubo que colgarle conteos en el
    DTO—. Con lotes habría además una fila por tanda, y una ejecución
    interrumpida dejaría filas `running` huérfanas para siempre. La trazabilidad
    va al log, y el ESTADO se lee de la base.

    `remaining` se consulta después de procesar, con el mismo predicado que
    eligió el lote. No es `total - procesadas`: si alguien falla, sigue
    pendiente, y esa es justo la información que necesita la UI para saber que
    tiene que parar en vez de dar vueltas.
    """

    processed: int
    created: int
    relocated: int
    failed: int
    remaining: int


@dataclass(frozen=True)
class FolderPlanEntry:
    """Qué haría el volcado con UNA persona, sin hacerlo.

    `action` es el veredicto:
      - `crear`      -> no tiene carpeta en ninguna parte
      - `mover`      -> existe SUELTA en la raíz (árbol plano heredado)
      - `recolocar`  -> existe, pero bajo una sociedad que ya no es la suya
    """

    user_id: str
    email: str
    entity_name: Optional[str]
    action: str


@dataclass(frozen=True)
class BulkFolderPlan:
    """Pasada EN SECO: lo que ocurriría, sin haber escrito nada.

    Solo habla del trabajo PENDIENTE. A quien ya tiene su carpeta en su sitio
    ni se le menciona ni se le consulta a Drive — antes se hacían ~7 llamadas
    por persona para acabar diciendo "esta no necesita nada", y eso hacía que
    el propio plan pudiera expirar. Ahora su coste es proporcional a lo que
    falta, así que tiende a cero según avanza el volcado.

    `entity_folders_to_create` van aparte porque se comparten entre personas:
    contarlas por empleado multiplicaría por 40 lo que son 4 carpetas.
    """

    entries: list[FolderPlanEntry]
    entity_folders_to_create: list[str]
    already_done: int

    @property
    def to_create(self) -> int:
        return sum(1 for e in self.entries if e.action == "crear")

    @property
    def to_move(self) -> int:
        return sum(1 for e in self.entries if e.action in ("mover", "recolocar"))

    @property
    def pending(self) -> int:
        return len(self.entries)

    @property
    def category_folders_to_create(self) -> int:
        """Cinco por carpeta que nazca. A quien solo se recoloca no se le
        crean: se mueve con las suyas dentro."""
        return CATEGORY_FOLDER_COUNT * self.to_create

    @property
    def estimated_drive_writes(self) -> int:
        """Escrituras que costaría aplicarlo. Es una COTA, no una promesa: si
        alguien pasa a activo entre el plan y el volcado, entra y suma."""
        return (
            len(self.entity_folders_to_create)
            + self.to_create
            + self.to_move
            + self.category_folders_to_create
        )
