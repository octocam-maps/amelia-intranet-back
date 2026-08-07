"""
Puertos (Protocols) del feature `documents`. `domain` no importa nada de
`infrastructure` ni de FastAPI — las implementaciones concretas (Postgres
para `IDocumentRepository`, Drive real o mock para `IDocumentStorage`) viven
en `infrastructure` y se inyectan aquí por duck typing estructural, igual
que el resto de puertos del proyecto.
"""

from typing import Optional, Protocol

from .models import (
    Document,
    DriveFileMetadata,
    PendingFolderWork,
    SyncRun,
    UploadedFile,
)


class DriveFileNotFoundError(Exception):
    """El `drive_file_id` no corresponde a ningún archivo en el proveedor de
    almacenamiento activo. Tanto `MockDocumentStorage` (WU-A) como el
    proveedor real de Google Drive (WU-B) deben levantar esta MISMA clase —
    así el caso de uso que traduce a 404 (WU-C1, `DownloadDocumentUseCase`)
    no necesita distinguir qué `DRIVE_PROVIDER` está activo."""


class IDocumentRepository(Protocol):
    async def find_by_id(self, document_id: str) -> Optional[Document]: ...

    async def list_for_user(
        self, user_id: str, *, category: Optional[str] = None
    ) -> list[Document]:
        """RGPD: SIEMPRE filtrado por `user_id` — nunca expone documentos de
        otro usuario (docs/permisos-roles.md). Excluye `deleted_at`."""
        ...

    async def list_all(
        self, *, category: Optional[str] = None, user_id: Optional[str] = None
    ) -> list[Document]:
        """Vista de administración (sin scoping por dueño). `user_id`
        opcional para que el admin filtre por un empleado concreto."""
        ...

    async def create(
        self,
        *,
        user_id: str,
        category: str,
        title: str,
        period: Optional[str],
        drive_file_id: Optional[str],
        mime_type: str,
        content_hash: Optional[str],
        uploaded_by: Optional[str],
    ) -> Document:
        """`uploaded_by=None` identifica una fila insertada por el sync
        automático (WU-D), no por la subida manual de un admin."""
        ...

    async def soft_delete(self, document_id: str) -> bool:
        """`UPDATE ... SET deleted_at = CURRENT_TIMESTAMP WHERE id = $1 AND
        deleted_at IS NULL` — `True` si borró una fila, `False` si ya estaba
        borrada o no existe. NUNCA borra/mueve el archivo en Drive (decisión
        de diseño: Drive lo gestiona RRHH directamente)."""
        ...

    async def find_drive_folder_id(self, user_id: str) -> Optional[str]:
        """Lee el `users.drive_folder_id` cacheado (migración 025)."""
        ...

    async def save_drive_folder_id(
        self,
        user_id: str,
        drive_folder_id: str,
        *,
        entity_id: Optional[str] = None,
    ) -> None:
        """Cachea el id de la subcarpeta resuelta la primera vez, para no
        volver a buscarla por nombre en cada subida/descarga.

        `entity_id` registra BAJO QUÉ sociedad quedó colocada [055]. Es lo que
        permite detectar después, sin preguntar a Drive, que alguien cambió de
        sociedad y su carpeta se quedó en la anterior."""
        ...

    async def find_entity_drive_folder_id(self, entity_id: str) -> Optional[str]:
        """`entities.drive_folder_id` [055] — gemelo del de `users`.

        Antes de existir esta columna, el id se resolvía preguntando a Drive
        por nombre en cada persona y se cacheaba en memoria del proveedor. Ese
        caché ocultaba el coste pero no el problema: dos peticiones simultáneas
        tienen dos cachés y crean dos carpetas homónimas, que Drive acepta sin
        rechistar."""
        ...

    async def save_entity_drive_folder_id(
        self, entity_id: str, drive_folder_id: str
    ) -> None:
        ...

    async def find_pending_folder_work(
        self, *, limit: Optional[int] = None
    ) -> list[PendingFolderWork]:
        """Quién necesita trabajo de carpeta ahora mismo: no la tiene, o la
        tiene bajo la sociedad equivocada.

        ES LA ÚNICA DEFINICIÓN de «pendiente» del feature. La usan el plan, el
        lote y el contador de restantes; si divergieran, la barra de progreso
        podría no llegar nunca a cero.

        `limit` acota el lote. Que el trabajo se pida troceado es lo que hace
        que la petición no pueda expirar: el volcado entero eran ~500 llamadas
        a Drive dentro de un solo HTTP, y el proxy lo cortaba a mitad."""
        ...

    async def count_provisionable_users(self) -> int:
        """Cuánta gente entra en el volcado en total (activos + invitados, sin
        bajas). Es el denominador de «12 de 37»: sin él la UI solo puede decir
        «quedan 25», que no permite saber si va por el principio o por el
        final."""
        ...

    async def count_pending_folder_work(self) -> int:
        """Cuántas quedan, con el MISMO predicado que `find_pending_folder_work`.

        Se calcula, no se lleva en un contador: un contador puede desincronizarse
        del estado real, y entonces la UI dice «faltan 3» para siempre."""
        ...

    def provisioning_lock(self):
        """Gestor de contexto asíncrono que cede `True` si se obtuvo el cerrojo
        de volcado, `False` si ya hay otro en curso.

        Existe porque dos administradores pulsando a la vez crearían carpetas
        duplicadas: cada petición resuelve por su cuenta si la carpeta de una
        sociedad existe, y ninguna ve lo que está haciendo la otra."""
        ...

    async def find_active_users_with_email(self) -> list[tuple[str, str, Optional[str]]]:
        """`(user_id, email, entity_name)` de empleados con `status='active'`
        — el sync (WU-D) itera solo sobre estos, nunca sobre externos-invitados
        ni usuarios de baja.

        `entity_name` es `None` para quien no tiene sociedad asignada (el
        externo-invitado): su carpeta cuelga de la raíz, no de ninguna
        entidad."""
        ...

    async def find_entity_for_user(
        self, user_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        """`(entity_id, entity_name)` de la sociedad a la que pertenece, o
        `(None, None)` si no tiene ninguna. Decide bajo qué carpeta de entidad
        va la suya en Drive.

        Devuelve también el `id` y no solo el nombre porque `entities.drive_folder_id`
        [055] se lee y se escribe por id — con el nombre habría que volver a la
        base a traducirlo."""
        ...

    async def create_sync_run(self) -> SyncRun:
        """Inserta una fila en `drive_sync_runs` con `status='running'`."""
        ...

    async def finish_sync_run(
        self,
        sync_run_id: str,
        *,
        status: str,
        files_synced: int,
        error_detail: Optional[str],
    ) -> SyncRun: ...


class IDocumentStorage(Protocol):
    """Puerto sobre el proveedor de almacenamiento del BINARIO (Google Drive
    real o `MockDocumentStorage`). Postgres nunca guarda el contenido del
    archivo, solo los metadatos vía `IDocumentRepository`."""

    async def get_or_create_entity_folder(self, entity_name: str) -> str:
        """Carpeta de una sociedad del grupo bajo la raíz, creándola si no
        existe. Es el nivel que agrupa a las personas por entidad."""
        ...

    async def get_or_create_employee_folder(
        self, email: str, *, entity_folder_id: Optional[str] = None
    ) -> str:
        """Id de la carpeta del empleado (nombre = `email`) DENTRO de
        `entity_folder_id`, creándola si no existe. Con `None` cuelga de la
        raíz — el externo-invitado no pertenece a ninguna sociedad.

        Recibe el id del padre YA RESUELTO, no el nombre de la sociedad: esa
        resolución vive en `application/entity_folders.py` porque necesita la
        base de datos, y el almacenamiento no la conoce. Mientras el puerto
        aceptaba un nombre, cada llamada acababa preguntando a Drive dónde
        estaba la carpeta de la sociedad.

        Si la carpeta ya existía suelta en la raíz (árbol plano anterior a la
        reorganización), se MUEVE conservando su id en vez de crear una
        nueva: `users.drive_folder_id` sigue apuntando a la misma y los
        documentos ya subidos no se pierden de vista."""
        ...

    async def find_entity_folder(self, entity_name: str) -> Optional[str]:
        """Carpeta de una sociedad SIN crearla. La usa la pasada en seco del
        provisioning para saber qué haría sin tocar Drive."""
        ...

    async def find_employee_folder(
        self, email: str, *, parent_id: Optional[str] = None
    ) -> Optional[str]:
        """Busca la subcarpeta por nombre = `email` SIN crearla — la usa el
        sync (WU-D): si RRHH todavía no colocó ninguna carpeta a mano para
        ese empleado, el sync simplemente no encuentra nada que conciliar,
        nunca crea una carpeta vacía.

        `parent_id` acota la búsqueda a una carpeta concreta (la de su
        entidad); sin él busca en la raíz, que es donde están las del árbol
        plano anterior a la reorganización. La pasada en seco necesita
        distinguir esos dos sitios para decidir entre "mover" y "crear"."""
        ...

    async def find_folder_parent_id(self, folder_id: str) -> Optional[str]:
        """Bajo qué carpeta cuelga `folder_id` HOY, según Drive.

        Solo se consulta para quien la base marca como pendiente de
        recolocación, que son pocos. Es lo que permite que el backfill de
        `users.drive_folder_entity_id` [055] sea optimista sin riesgo: si la
        suposición era errónea, aquí se ve y no se mueve nada de más."""
        ...

    async def move_folder(self, folder_id: str, *, new_parent_id: str) -> None:
        """Recoloca una carpeta CONSERVANDO su id y su contenido.

        Que el id no cambie es la razón de mover en vez de crear en el sitio
        nuevo: `users.drive_folder_id` sigue siendo válido y las nóminas ya
        subidas viajan con la carpeta. Crear una nueva dejaría al backend
        subiendo a la vieja y a la persona mirando la nueva, vacía."""
        ...

    async def get_or_create_category_folder(
        self, employee_folder_id: str, category: str
    ) -> str:
        """Devuelve el id de la subcarpeta de categoría (nombre EXACTO según
        `domain.models.CATEGORY_FOLDER_NAMES` — `payslip`->"Nóminas",
        `contract`->"Contratos", `general`->"General", `other`->"Otros")
        DENTRO de `employee_folder_id`, CREÁNDOLA si no existe. La usa la
        subida manual (`UploadDocumentUseCase`): el admin siempre puede
        subir aunque sea el primer documento de esa categoría para esa
        persona. `category` llega ya validada contra `DOCUMENT_CATEGORIES`
        por el use case — este puerto no la revalida."""
        ...

    async def find_category_folder(
        self, employee_folder_id: str, category: str
    ) -> Optional[str]:
        """Busca la subcarpeta de categoría DENTRO de `employee_folder_id`
        SIN crearla — mismo criterio que `find_employee_folder` frente a
        `get_or_create_employee_folder`. La usa el sync (`SyncDocumentsUseCase`):
        si esa categoría todavía no tiene subcarpeta para ese empleado, el
        sync no tiene nada que conciliar ahí, nunca crea una vacía."""
        ...

    async def upload(
        self, *, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> UploadedFile:
        """Sube el archivo a la subcarpeta indicada. La implementación real
        decide multipart simple (≤5MB) vs. resumible (>5MB) — el puerto no
        expone esa distinción, es un detalle del adaptador de Drive."""
        ...

    async def download(self, drive_file_id: str) -> bytes:
        """Descarga el archivo COMPLETO a memoria. Solo se usa con ficheros
        ≤ `DOCUMENTS_MAX_UPLOAD_MB` (validado en el use case, WU-C1).
        Levanta `DriveFileNotFoundError` si `drive_file_id` no existe."""
        ...

    async def list_folder_files(self, folder_id: str) -> list[DriveFileMetadata]:
        """Lista TODOS los archivos de la subcarpeta, sin filtrar — el
        filtro de negocio (mimeType/tamaño) para el sync vive en el use
        case (WU-D), no en este puerto."""
        ...
