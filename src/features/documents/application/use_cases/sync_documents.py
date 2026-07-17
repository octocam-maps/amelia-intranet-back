"""
Caso de uso: sincronizar (conciliar) Drive -> Postgres. RRHH coloca archivos
directamente en la subcarpeta de Drive de cada empleado (fuera de la app,
`sdd/fase4-nominas-documentos/design`); este caso de uso detecta los que
todavía no están indexados en `employee_documents` y crea su fila de
metadata (`uploaded_by=None`, identifica una fila del sync automático).

Disparado por `POST /documents/sync`, protegido con
`require_role("administrador")` en la capa de FastAPI (mismo criterio que
`UploadDocumentUseCase`) — no repite el chequeo de rol aquí.

Alcance de esta work-unit (WU-D): SOLO altas (Drive -> Postgres). No
soft-borra filas cuyo `drive_file_id` ya no aparece en el listado de Drive
— el diseño lo menciona como posible extensión, pero borrar metadatos por
ausencia en un listado es una operación demasiado sensible para inferirla
sin que el equipo confirme la política de retención (ver Open Questions de
`sdd/fase4-nominas-documentos/design`).
"""

import logging
import re
from typing import Optional

from ...domain.models import SyncRun
from ...domain.ports import IDocumentRepository, IDocumentStorage

logger = logging.getLogger(__name__)

_ALLOWED_MIME_TYPE = "application/pdf"

# Convención de nombre para la categorización automática del sync
# (`sdd/fase4-nominas-documentos/design`): `NOMINA_YYYY-MM*` -> payslip (con
# período), `CONTRATO*` -> contract, cualquier otro nombre -> general.
# Case-insensitive: RRHH no siempre respeta mayúsculas al colocar el archivo
# a mano.
_PAYSLIP_PATTERN = re.compile(r"^NOMINA[_\-\s]?(\d{4}-\d{2})", re.IGNORECASE)
_CONTRACT_PATTERN = re.compile(r"^CONTRATO", re.IGNORECASE)


def _categorize(filename: str) -> tuple[str, Optional[str]]:
    # Se compara sobre el nombre sin extensión para que un `.PDF` en
    # mayúsculas no interfiera con el patrón.
    stem = filename.rsplit(".", 1)[0]
    payslip_match = _PAYSLIP_PATTERN.match(stem)
    if payslip_match:
        return "payslip", payslip_match.group(1)
    if _CONTRACT_PATTERN.match(stem):
        return "contract", None
    return "general", None


class SyncDocumentsUseCase:
    def __init__(
        self,
        repository: IDocumentRepository,
        storage: IDocumentStorage,
        max_upload_mb: int,
    ):
        self._repository = repository
        self._storage = storage
        # Mismo límite que la subida manual (`UploadDocumentUseCase`) — un
        # PDF colocado a mano que lo supere se omite, no rompe el sync.
        self._max_upload_bytes = max_upload_mb * 1024 * 1024

    async def execute(self) -> SyncRun:
        sync_run = await self._repository.create_sync_run()

        active_users = await self._repository.find_active_users_with_email()
        created = 0
        skipped = 0
        failed_employees = 0

        for user_id, email in active_users:
            try:
                employee_created, employee_skipped = await self._sync_employee(user_id, email)
            except Exception:
                # Best-effort por empleado: un fallo puntual (p. ej. Drive
                # devuelve error para esa subcarpeta) no debe abortar el
                # resto del sync — se loguea y se sigue con el siguiente.
                failed_employees += 1
                logger.exception(
                    "Fallo al sincronizar documentos de Drive para user_id=%s", user_id
                )
                continue
            created += employee_created
            skipped += employee_skipped

        if not active_users or failed_employees == 0:
            status = "success"
        elif failed_employees == len(active_users):
            status = "failed"
        else:
            status = "partial"

        detail_parts = []
        if skipped:
            detail_parts.append(f"{skipped} archivo(s) omitido(s) por tamaño o tipo no admitido.")
        if failed_employees:
            detail_parts.append(f"{failed_employees} empleado(s) fallaron durante el sync.")

        return await self._repository.finish_sync_run(
            sync_run.id,
            status=status,
            files_synced=created,
            error_detail=" ".join(detail_parts) or None,
        )

    async def _sync_employee(self, user_id: str, email: str) -> tuple[int, int]:
        # La subcarpeta se cachea en `users.drive_folder_id` (migración 025)
        # igual que en `UploadDocumentUseCase`, pero AQUÍ se resuelve sin
        # crearla (`find_employee_folder`, no `get_or_create_...`): si RRHH
        # todavía no colocó ninguna carpeta a mano, el sync no tiene nada
        # que conciliar para ese empleado.
        folder_id = await self._repository.find_drive_folder_id(user_id)
        if folder_id is None:
            folder_id = await self._storage.find_employee_folder(email)
            if folder_id is None:
                return 0, 0
            await self._repository.save_drive_folder_id(user_id, folder_id)

        existing_drive_file_ids = {
            document.drive_file_id
            for document in await self._repository.list_for_user(user_id)
            if document.drive_file_id
        }

        created = 0
        skipped = 0
        for drive_file in await self._storage.list_folder_files(folder_id):
            if drive_file.drive_file_id in existing_drive_file_ids:
                continue
            if (
                drive_file.mime_type != _ALLOWED_MIME_TYPE
                or drive_file.size_bytes > self._max_upload_bytes
            ):
                skipped += 1
                continue

            category, period = _categorize(drive_file.name)
            await self._repository.create(
                user_id=user_id,
                category=category,
                title=drive_file.name,
                period=period,
                drive_file_id=drive_file.drive_file_id,
                mime_type=drive_file.mime_type,
                content_hash=drive_file.content_hash,
                uploaded_by=None,
            )
            created += 1

        return created, skipped
