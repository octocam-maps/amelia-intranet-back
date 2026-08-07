"""DTOs de request/response (Pydantic) del feature `documents`. La subida
(`POST /documents`) es multipart (archivo + campos de formulario) — no lleva
DTO de request propio, sus campos se declaran como `Form(...)`/`File(...)`
directamente en `routes.py` (mismo criterio que el resto del ecosistema
FastAPI para endpoints con archivo)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from ..application.use_cases.bulk_provision_drive_folders import DEFAULT_BATCH_LIMIT


class DocumentDTO(BaseModel):
    id: str
    user_id: str
    category: str
    title: str
    period: Optional[str] = None
    mime_type: str
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    created_at: datetime


class DocumentListDTO(BaseModel):
    documents: list[DocumentDTO]


class SyncRunDTO(BaseModel):
    """Resumen de una corrida de `POST /documents/sync` (WU-D) — mapea
    `drive_sync_runs` tal cual, sin desglose de omitidos/fallidos por
    empleado (ese detalle va en `error_detail` como texto, no hay columnas
    dedicadas en el esquema, `004_documents.sql`)."""

    id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    files_synced: int
    error_detail: Optional[str] = None


class FolderBatchRequestDTO(BaseModel):
    """Cuerpo de un lote. `limit` viaja en la petición y no en configuración
    porque es la UI quien conoce su propia tolerancia de espera; el caso de uso
    lo acota igualmente entre 1 y `MAX_BATCH_LIMIT`."""

    limit: int = DEFAULT_BATCH_LIMIT


class FolderBatchResultDTO(BaseModel):
    """Resultado de UN lote.

    `remaining` es lo que gobierna el bucle del cliente, y se calcula
    consultando la base después de procesar — no es `total - procesadas`. Quien
    falla sigue pendiente, y esa diferencia es justo la señal de que hay que
    dejar de repetir."""

    processed: int
    created: int
    relocated: int
    failed: int
    remaining: int


class FolderPlanEntryDTO(BaseModel):
    """Una línea de la pasada en seco. `action`: `crear` | `mover` |
    `recolocar`."""

    user_id: str
    email: str
    entity_name: Optional[str]
    action: str


class BulkFolderPlanDTO(BaseModel):
    """Qué haría el volcado, SIN haberlo hecho. Solo habla del trabajo
    pendiente: a quien ya tiene su carpeta en su sitio ni se le menciona."""

    entries: list[FolderPlanEntryDTO]
    entity_folders_to_create: list[str]
    pending: int
    already_done: int
    to_create: int
    to_move: int
    category_folders_to_create: int
    estimated_drive_writes: int
