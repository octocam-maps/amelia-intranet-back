"""
Volcado de carpetas de Drive, POR LOTES.

`POST /documents/provision-folders` procesa como mucho `limit` personas
pendientes y devuelve cuántas quedan; la UI repite hasta cero. Protegido con
`require_role("administrador")` en la capa de FastAPI, mismo criterio que
`SyncDocumentsUseCase` — no se repite el chequeo aquí.

## Por qué por lotes y no de una vez

Cada persona son ~13 llamadas a Drive. La plantilla entera eran ~500 dentro de
UNA petición HTTP: más de dos minutos, y el proxy la cortaba con un 504. El
intento de arreglarlo paralelizando trajo un fallo peor —el cliente de Google
no es seguro entre hilos— que se manifestaba como errores de red aleatorios.

Trocear ataca la causa en vez del síntoma: **cada petición es lo bastante
pequeña como para no poder expirar**. Además sale gratis lo que antes habría
que construir a mano: es reanudable, sobrevive a un redespliegue a mitad, y no
deja ningún estado que limpiar si se corta.

## Por qué no hay fila de run

El progreso se DERIVA de la base (`count_pending_folder_work`), no se lleva en
un contador. Un contador puede desincronizarse del estado real y entonces la
barra nunca llega a cero; una consulta no puede mentir. Y sin fila de run no
hay filas `running` huérfanas que limpiar cuando el proceso muera a mitad.

## Qué cubre

- Quien nunca tuvo carpeta: altas anteriores al hook, hooks que fallaron, y
  usuarios creados al aceptar una invitación — esos NO disparan el hook (ver
  `LoginWithGoogleUseCase`).
- Quien **cambió de sociedad**: su carpeta se mueve a la nueva, conservando id
  y contenido. Antes era invisible, porque el provisioning cortaba en cuanto
  veía un `drive_folder_id` cacheado.
"""

import asyncio
import logging
from typing import Optional

from ...domain.models import PendingFolderWork
from ...domain.ports import IDocumentRepository, IDocumentStorage
from ..entity_folders import resolve_entity_folder_id
from ..results import BulkFolderPlan, FolderBatchResult, FolderPlanEntry
from .provision_employee_drive_folder import ProvisionEmployeeDriveFolderUseCase

logger = logging.getLogger(__name__)

# Personas por lote. Con ~13 llamadas a Drive cada una, 10 son ~130 llamadas:
# unos pocos segundos, muy lejos de cualquier timeout de proxy.
DEFAULT_BATCH_LIMIT = 10
MAX_BATCH_LIMIT = 50

# Personas provisionándose a la vez DENTRO de un lote. Es una optimización, no
# un requisito: bajarlo a 1 debe seguir funcionando, y hay test que lo cubre.
# Que la corrección no dependa de la velocidad es justo lo que faltaba antes.
#
# TIENE QUE QUEDAR MUY POR DEBAJO DEL POOL DE CONEXIONES (`max_size=10`, ver
# `asyncpg_pool`), que es de TODA la aplicación. Medido: con 8 el pico durante
# un lote era de 8 conexiones y dejaba 2 libres para el resto de la intranet
# durante varios segundos — el volcado no reventaba, pero encolaba a los demás.
# Con 4 el pico baja a la mitad y un lote de 10 personas sigue tardando
# segundos, que para algo que se lanza unas pocas veces al año sobra.
MAX_CONCURRENT_PROVISIONS = 4


class ProvisioningBusyError(Exception):
    """Ya hay otro volcado en curso. Se traduce a 409 en la capa HTTP.

    No es una cortesía: dos volcados simultáneos resuelven por su cuenta si la
    carpeta de una sociedad existe, ninguno ve lo que hace el otro, y Drive
    acepta dos carpetas con el mismo nombre sin dar ningún error."""


class BulkProvisionDriveFoldersUseCase:
    def __init__(self, repository: IDocumentRepository, storage: IDocumentStorage):
        self._repository = repository
        self._storage = storage
        self._provision = ProvisionEmployeeDriveFolderUseCase(repository, storage)

    # --- Pasada en seco ----------------------------------------------------

    async def plan(self) -> BulkFolderPlan:
        """Qué haría, sin escribir nada.

        Solo consulta a Drive por quien NO tiene carpeta registrada, y una vez:
        para distinguir "hay que crearla" de "existe suelta en la raíz y hay
        que moverla". Ese segundo caso es herencia del árbol plano y desaparece
        tras el primer volcado completo, así que el coste del plan tiende a
        cero según avanza el trabajo.
        """
        pending = await self._repository.find_pending_folder_work()
        total = await self._repository.count_provisionable_users()

        entities_to_create: list[str] = []
        entidades_vistas: set[str] = set()
        entries: list[FolderPlanEntry] = []

        for work in pending:
            if (
                work.entity_id is not None
                and work.entity_name is not None
                and work.entity_id not in entidades_vistas
            ):
                entidades_vistas.add(work.entity_id)
                if await self._repository.find_entity_drive_folder_id(work.entity_id) is None:
                    entities_to_create.append(work.entity_name)

            if work.drive_folder_id is not None:
                # Tiene carpeta registrada y aun así está pendiente: la única
                # forma de que eso pase es que haya cambiado de sociedad.
                action = "recolocar"
            else:
                flat = await self._storage.find_employee_folder(work.email)
                action = "mover" if flat is not None else "crear"

            entries.append(
                FolderPlanEntry(
                    user_id=work.user_id,
                    email=work.email,
                    entity_name=work.entity_name,
                    action=action,
                )
            )

        return BulkFolderPlan(
            entries=entries,
            entity_folders_to_create=entities_to_create,
            already_done=max(0, total - len(pending)),
        )

    # --- Un lote -----------------------------------------------------------

    async def execute(self, *, limit: int = DEFAULT_BATCH_LIMIT) -> FolderBatchResult:
        limit = max(1, min(limit, MAX_BATCH_LIMIT))

        async with self._repository.provisioning_lock() as acquired:
            if not acquired:
                raise ProvisioningBusyError(
                    "Ya hay un volcado de carpetas en curso. Espera a que termine."
                )

            pending = await self._repository.find_pending_folder_work(limit=limit)
            if not pending:
                return FolderBatchResult(
                    processed=0, created=0, relocated=0, failed=0, remaining=0
                )

            semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROVISIONS)
            outcomes = await asyncio.gather(
                *(self._process_one(semaphore, work) for work in pending)
            )

            created = sum(1 for outcome in outcomes if outcome == "created")
            relocated = sum(1 for outcome in outcomes if outcome == "relocated")
            failed = sum(1 for outcome in outcomes if outcome is None)

            # DESPUÉS de procesar y con el MISMO predicado que eligió el lote:
            # quien falló sigue contando como pendiente, que es exactamente lo
            # que la UI necesita saber para dejar de dar vueltas.
            remaining = await self._repository.count_pending_folder_work()

        return FolderBatchResult(
            processed=len(pending),
            created=created,
            relocated=relocated,
            failed=failed,
            remaining=remaining,
        )

    async def _process_one(
        self, semaphore: asyncio.Semaphore, work: PendingFolderWork
    ) -> Optional[str]:
        """`"created"` / `"relocated"` / `None` si falló.

        Devuelve `None` en vez de propagar: con `asyncio.gather`, una excepción
        sin capturar CANCELA a las hermanas, así que una persona tumbaría al
        lote entero. Best-effort por empleado, mismo criterio que
        `SyncDocumentsUseCase._sync_employee`.
        """
        async with semaphore:
            try:
                if work.drive_folder_id is not None:
                    return await self._relocate(work)
                result = await self._provision.execute(
                    user_id=work.user_id,
                    email=work.email,
                    entity_id=work.entity_id,
                    entity_name=work.entity_name,
                )
                # Se informa de lo que PASÓ, no de lo que se intentó: el caso
                # de uso corta sin tocar Drive si el id ya estaba cacheado, y
                # dar eso por "creada" haría que el resumen contase carpetas
                # que nadie creó.
                return "created" if result.created else "skipped"
            except Exception:
                logger.exception(
                    "Fallo al provisionar la carpeta de Drive de user_id=%s", work.user_id
                )
                return None

    async def _relocate(self, work: PendingFolderWork) -> str:
        """Su carpeta existe, pero cuelga de la sociedad anterior.

        Se VERIFICA el padre real en Drive antes de mover. Eso es lo que hace
        inofensivo el backfill optimista de la migración `055`: si la columna
        mentía y la carpeta ya estaba en su sitio, aquí se descubre y solo se
        corrige el dato, sin escribir en Drive.
        """
        assert work.drive_folder_id is not None

        destino = await resolve_entity_folder_id(
            self._repository,
            self._storage,
            entity_id=work.entity_id,
            entity_name=work.entity_name,
        )
        padre_actual = await self._storage.find_folder_parent_id(work.drive_folder_id)

        # SIN guarda de `destino is not None`. `None` significa "la raíz" en
        # todo el puerto, así que quedarse quieto cuando alguien PIERDE su
        # sociedad dejaba su carpeta bajo la anterior mientras la base decía
        # que estaba en la raíz — y el predicado ya no lo volvía a detectar,
        # porque NULL frente a NULL no es distinto. Divergencia silenciosa y
        # permanente: exactamente lo que este rediseño venía a eliminar.
        if padre_actual != destino:
            # Mover conserva el id y el contenido: `users.drive_folder_id`
            # sigue siendo válido y las nóminas viajan con la carpeta.
            await self._storage.move_folder(work.drive_folder_id, new_parent_id=destino)

        await self._repository.save_drive_folder_id(
            work.user_id, work.drive_folder_id, entity_id=work.entity_id
        )
        return "relocated"
