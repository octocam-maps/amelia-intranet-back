"""
Caso de uso: provisionar la carpeta PADRE de Google Drive de un empleado
(nombre = email), cacheando su id en `users.drive_folder_id` (migración
025). Núcleo IDEMPOTENTE reusado por dos disparadores (decisión de producto
"hook en alta + batch de backfill"):

- `CreateStaffMemberUseCase` (feature `staff`) lo invoca best-effort tras el
  alta de cada persona nueva — ver `staff.domain.ports.IDriveFolderProvisioner`
  y su adaptador en `staff/infrastructure/dependencies.py`.
- `BulkProvisionDriveFoldersUseCase` (este mismo feature) lo invoca en batch
  para el backfill de empleados que ya existían antes de este hook, o cuyo
  hook falló en su momento (best-effort, re-ejecutable).

Alcance: SOLO la carpeta PADRE del empleado. Las subcarpetas de categoría
(Nóminas/Contratos/General/Otros/Firmados) siguen siendo 100% lazy — se
crean en el primer upload de esa categoría (`UploadDocumentUseCase`,
`get_or_create_category_folder`). Pre-crearlas aquí no es trivial (harían
falta 5 llamadas más a Drive por empleado, incluso para categorías que esa
persona podría no usar nunca, p. ej. `contract` para alguien sin contrato
todavía) — se deja fuera de esta unidad, tal como decidió el equipo.
"""

from dataclasses import dataclass

from ...domain.ports import IDocumentRepository, IDocumentStorage


@dataclass(frozen=True)
class ProvisionFolderResult:
    """`created=False` cuando el id ya estaba cacheado (no-op, sin llamar a
    Drive) — lo usa `BulkProvisionDriveFoldersUseCase` para distinguir
    "creada" de "omitida" en el resumen del batch."""

    drive_folder_id: str
    created: bool


class ProvisionEmployeeDriveFolderUseCase:
    def __init__(self, repository: IDocumentRepository, storage: IDocumentStorage):
        self._repository = repository
        self._storage = storage

    async def execute(self, *, user_id: str, email: str) -> ProvisionFolderResult:
        existing_folder_id = await self._repository.find_drive_folder_id(user_id)
        if existing_folder_id is not None:
            return ProvisionFolderResult(drive_folder_id=existing_folder_id, created=False)

        folder_id = await self._storage.get_or_create_employee_folder(email)
        await self._repository.save_drive_folder_id(user_id, folder_id)
        return ProvisionFolderResult(drive_folder_id=folder_id, created=True)
