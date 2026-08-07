"""
Caso de uso: batch de backfill de carpetas de Drive (decisión de producto
"hook en alta + batch de backfill"). Recorre los empleados activos **y los
invitados** (`find_provisionable_users_with_email`, distinto del que usa
`SyncDocumentsUseCase` — ver su docstring en el puerto) y provisiona la
carpeta de cada uno reusando el núcleo idempotente
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

import asyncio
import logging
from typing import Optional

from ...domain.models import CATEGORY_FOLDER_NAMES, SyncRun
from ...domain.ports import IDocumentRepository, IDocumentStorage
from ..results import BulkFolderPlan, BulkFolderProvisionResult, FolderPlanEntry
from .provision_employee_drive_folder import ProvisionEmployeeDriveFolderUseCase

logger = logging.getLogger(__name__)

# Personas provisionándose a la vez. Cada una son ~14 llamadas a Drive, y en
# serie las 37 de la plantilla se iban a más de dos minutos con la petición
# HTTP abierta — por encima del timeout habitual de un proxy.
#
# El número es deliberadamente conservador. Lo que se gana subiéndolo se
# pierde entero en cuanto Google devuelve un `rateLimitExceeded`: el batch es
# best-effort, así que esa persona se cuenta como fallida y hay que repetir.
# Con 8, las 37 caben en ~5 tandas y se queda muy lejos de cualquier límite.
MAX_CONCURRENT_PROVISIONS = 8


class BulkProvisionDriveFoldersUseCase:
    def __init__(self, repository: IDocumentRepository, storage: IDocumentStorage):
        self._repository = repository
        # `plan()` consulta Drive directamente (sin crear nada), así que
        # necesita el storage además del caso de uso que sí escribe.
        self._storage = storage
        self._provision = ProvisionEmployeeDriveFolderUseCase(repository, storage)

    async def plan(self) -> BulkFolderPlan:
        """Pasada EN SECO: qué haría, sin tocar Drive.

        Existe porque la primera ejecución real sobre un Drive ya poblado
        mueve carpetas de sitio, y para eso no hay deshacer. Consulta (nunca
        crea) y devuelve el veredicto por persona más el coste en escrituras,
        que es el dato que decide si conviene lanzarlo de una vez o por
        tandas: Drive limita las escrituras y un `rateLimitExceeded` a mitad
        del batch deja el árbol a medias.
        """
        active_users = await self._repository.find_provisionable_users_with_email()

        entity_folders: dict[str, Optional[str]] = {}
        entities_to_create: list[str] = []
        entries: list[FolderPlanEntry] = []

        for user_id, email, entity_name in active_users:
            # Cachea la consulta por entidad: son 4 sociedades para ~40
            # personas, y preguntarlo por cada una serían 40 llamadas para
            # saber lo mismo.
            if entity_name is not None and entity_name not in entity_folders:
                found = await self._storage.find_entity_folder(entity_name)
                entity_folders[entity_name] = found
                if found is None:
                    entities_to_create.append(entity_name)

            entity_folder_id = entity_folders.get(entity_name) if entity_name else None

            cached = await self._repository.find_drive_folder_id(user_id)
            if cached is not None:
                # Mismo atajo que la ejecución real: con el id cacheado ni se
                # pregunta a Drive.
                entries.append(
                    FolderPlanEntry(
                        user_id=user_id,
                        email=email,
                        entity_name=entity_name,
                        action="ya_registrada",
                        missing_categories=await self._missing_categories(cached),
                    )
                )
                continue

            in_place = (
                await self._storage.find_employee_folder(email, parent_id=entity_folder_id)
                if entity_folder_id is not None
                else None
            )
            if in_place is not None:
                action, folder_id = "ya_en_su_sitio", in_place
            else:
                flat = await self._storage.find_employee_folder(email)
                if flat is not None and entity_name is not None:
                    action, folder_id = "mover", flat
                elif flat is not None:
                    action, folder_id = "ya_en_su_sitio", flat
                else:
                    action, folder_id = "crear", None

            entries.append(
                FolderPlanEntry(
                    user_id=user_id,
                    email=email,
                    entity_name=entity_name,
                    action=action,
                    # Una carpeta que aún no existe necesita las cinco.
                    missing_categories=(
                        list(CATEGORY_FOLDER_NAMES)
                        if folder_id is None
                        else await self._missing_categories(folder_id)
                    ),
                )
            )

        return BulkFolderPlan(entries=entries, entity_folders_to_create=entities_to_create)

    async def _missing_categories(self, employee_folder_id: str) -> list[str]:
        missing = []
        for category in CATEGORY_FOLDER_NAMES:
            if await self._storage.find_category_folder(employee_folder_id, category) is None:
                missing.append(category)
        return missing

    async def _provision_one(
        self,
        semaphore: "asyncio.Semaphore",
        user_id: str,
        email: str,
        entity_name: Optional[str],
    ):
        """Una persona, con el hueco de concurrencia ya pedido.

        Devuelve `None` en vez de propagar: best-effort por empleado, mismo
        criterio que `SyncDocumentsUseCase._sync_employee` — un fallo puntual
        (Drive no responde para esa persona) no debe abortar el resto.
        """
        async with semaphore:
            try:
                # `entity_name` viaja desde la misma consulta que los emails:
                # resolverlo aquí por persona serían N consultas más para un
                # dato que el repositorio ya tenía delante.
                return await self._provision.execute(
                    user_id=user_id, email=email, entity_name=entity_name
                )
            except Exception:
                logger.exception(
                    "Fallo al provisionar la carpeta de Drive de user_id=%s", user_id
                )
                return None

    async def execute(self) -> BulkFolderProvisionResult:
        sync_run = await self._repository.create_sync_run()

        active_users = await self._repository.find_provisionable_users_with_email()
        created = 0
        skipped = 0
        failed = 0

        # Las carpetas de ENTIDAD, antes del fan-out y de una en una.
        #
        # No es una optimización, es lo que hace seguro el paralelismo: dos
        # corrutinas que preguntan a la vez "¿existe ya Hincator?" reciben las
        # dos que no, y crean DOS carpetas con el mismo nombre. A partir de
        # ahí media plantilla cuelga de una y media de la otra, y Drive no se
        # queja porque admite nombres repetidos.
        #
        # Resolverlas aquí las deja además cacheadas en el proveedor, así que
        # las 37 personas siguientes no vuelven a preguntar por ellas.
        for entity_name in dict.fromkeys(
            entity for _, _, entity in active_users if entity is not None
        ):
            try:
                await self._storage.get_or_create_entity_folder(entity_name)
            except Exception:
                # Si la entidad no se puede crear, sus empleados fallarán uno
                # a uno y se contarán como tales — no se aborta el batch, que
                # puede tener gente de otras sociedades.
                logger.exception("Fallo al resolver la carpeta de la entidad %s", entity_name)

        # El resto, en paralelo acotado: son ~14 llamadas a Drive por persona
        # y en serie se iban a más de dos minutos, por encima del timeout del
        # proxy. El semáforo evita el otro extremo: soltar 37 tandas a la vez
        # es la forma más rápida de que Google devuelva `rateLimitExceeded`.
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROVISIONS)
        results = await asyncio.gather(
            *(
                self._provision_one(semaphore, user_id, email, entity_name)
                for user_id, email, entity_name in active_users
            )
        )

        for result in results:
            if result is None:
                failed += 1
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
