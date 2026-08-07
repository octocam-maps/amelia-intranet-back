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

Alcance (ampliado el 2026-08-06, decisión del team-lead): la carpeta del
empleado va DENTRO de la de su entidad, y se pre-crean las cinco subcarpetas
de categoría (Nóminas/Contratos/General/Otros/Firmados).

Antes eran 100% lazy —se creaban en el primer upload de cada categoría— y el
motivo escrito aquí era el coste: 5 llamadas más a Drive por empleado, incluso
para categorías que esa persona podría no usar nunca. Se acepta ese coste
porque el síntoma contrario era peor: RRHH abría la carpeta de alguien recién
dado de alta, la veía vacía y no podía distinguirlo de un fallo del
provisioning. Con ~40 personas, 200 llamadas de una vez son irrelevantes.

El árbol resultante:

    RAÍZ / <Entidad> / <email> / {Nóminas, Contratos, General, Otros, Firmados}
"""

import logging
from dataclasses import dataclass
from typing import Optional

from ...domain.models import CATEGORY_FOLDER_NAMES
from ...domain.ports import IDocumentRepository, IDocumentStorage
from ..entity_folders import resolve_entity_folder_id

logger = logging.getLogger(__name__)


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

    async def execute(
        self,
        *,
        user_id: str,
        email: str,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
    ) -> ProvisionFolderResult:
        existing_folder_id = await self._repository.find_drive_folder_id(user_id)
        if existing_folder_id is not None:
            return ProvisionFolderResult(drive_folder_id=existing_folder_id, created=False)

        # `entity_id`/`entity_name` pueden venir resueltos por quien llama (el
        # volcado los trae en la misma consulta que los emails, para no hacer
        # una por persona); si no, se resuelven aquí.
        if entity_id is None:
            entity_id, entity_name = await self._repository.find_entity_for_user(user_id)

        entity_folder_id = await resolve_entity_folder_id(
            self._repository,
            self._storage,
            entity_id=entity_id,
            entity_name=entity_name,
        )
        folder_id = await self._storage.get_or_create_employee_folder(
            email, entity_folder_id=entity_folder_id
        )
        # Se registra BAJO QUÉ sociedad quedó: es lo que permite detectar
        # después un cambio de sociedad sin preguntarle a Drive por cada
        # persona de la plantilla.
        await self._repository.save_drive_folder_id(
            user_id, folder_id, entity_id=entity_id
        )

        # Las cinco subcarpetas, para que la carpeta no se vea vacía y
        # RRHH pueda dejar un documento en su sitio desde el primer día.
        # Best-effort: si Drive falla en una, la carpeta del empleado ya está
        # creada y registrada, que es lo que importa — el primer upload de esa
        # categoría la crearía igualmente (`get_or_create_category_folder`).
        for category in CATEGORY_FOLDER_NAMES:
            try:
                await self._storage.get_or_create_category_folder(folder_id, category)
            except Exception:
                logger.exception(
                    "No se pudo pre-crear la subcarpeta '%s' de user_id=%s", category, user_id
                )

        return ProvisionFolderResult(drive_folder_id=folder_id, created=True)
