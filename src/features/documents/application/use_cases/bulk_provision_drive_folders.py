"""
Caso de uso: batch de backfill de carpetas de Drive (decisión de producto
"hook en alta + batch de backfill"). Recorre los empleados ACTIVOS
(`find_active_users_with_email`, mismo método que usa `SyncDocumentsUseCase`)
y provisiona la carpeta de cada uno reusando el núcleo idempotente
`ProvisionEmployeeDriveFolderUseCase` — cubre:

- Empleados dados de alta ANTES de que existiera el hook de
  `CreateStaffMemberUseCase`.
- Empleados cuyo hook falló en su momento (Drive caído, credenciales, etc.)
  — best-effort, así que el batch es su mecanismo de retry.
- Usuarios auto-provisionados/aceptados por invitación en el primer login
  (`LoginWithGoogleUseCase.create_user_from_invitation` /
  `create_auto_provisioned_user`): esos altas NO disparan el hook (decisión
  de alcance de esta unidad, ver docstring de `LoginWithGoogleUseCase` —
  enganchar ahí complicaría el layering de `auth.application`, que hoy no
  conoce ningún puerto de `documents`/`staff`); quedan cubiertos por este
  batch o por el primer upload manual.

Disparado por `POST /documents/provision-folders`, protegido con
`require_role("administrador")` en la capa de FastAPI (mismo criterio que
`SyncDocumentsUseCase`) — no repite el chequeo de rol aquí.

Idempotente y re-ejecutable (sirve de retry): un empleado que ya tiene
`drive_folder_id` cacheado se cuenta como "omitido", nunca vuelve a llamar a
Drive (`ProvisionEmployeeDriveFolderUseCase`). Best-effort por empleado: un
fallo puntual no aborta el resto del batch, se cuenta y se sigue.
"""

import logging

from ...domain.models import SyncRun
from ...domain.ports import IDocumentRepository, IDocumentStorage
from ..results import BulkFolderProvisionResult
from .provision_employee_drive_folder import ProvisionEmployeeDriveFolderUseCase

logger = logging.getLogger(__name__)


class BulkProvisionDriveFoldersUseCase:
    def __init__(self, repository: IDocumentRepository, storage: IDocumentStorage):
        self._repository = repository
        self._provision = ProvisionEmployeeDriveFolderUseCase(repository, storage)

    async def execute(self) -> BulkFolderProvisionResult:
        sync_run = await self._repository.create_sync_run()

        active_users = await self._repository.find_active_users_with_email()
        created = 0
        skipped = 0
        failed = 0

        for user_id, email in active_users:
            try:
                result = await self._provision.execute(user_id=user_id, email=email)
            except Exception:
                # Best-effort por empleado: mismo criterio que
                # `SyncDocumentsUseCase._sync_employee` — un fallo puntual
                # (p. ej. Drive no responde para esa persona) no debe abortar
                # el resto del batch.
                failed += 1
                logger.exception(
                    "Fallo al provisionar la carpeta de Drive de user_id=%s", user_id
                )
                continue

            if result.created:
                created += 1
            else:
                skipped += 1

        if not active_users or failed == 0:
            status = "success"
        elif failed == len(active_users):
            status = "failed"
        else:
            status = "partial"

        detail_parts = []
        if skipped:
            detail_parts.append(f"{skipped} carpeta(s) omitida(s) (ya existían).")
        if failed:
            detail_parts.append(f"{failed} empleado(s) fallaron durante el provisioning.")

        finished_run: SyncRun = await self._repository.finish_sync_run(
            sync_run.id,
            status=status,
            files_synced=created,
            error_detail=" ".join(detail_parts) or None,
        )

        return BulkFolderProvisionResult(
            sync_run=finished_run, created=created, skipped=skipped, failed=failed
        )
