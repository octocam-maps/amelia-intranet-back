"""
Resolución de la carpeta de Drive de una SOCIEDAD, en un solo sitio.

Lo comparten el volcado (`BulkProvisionDriveFoldersUseCase`), el alta
individual (`ProvisionEmployeeDriveFolderUseCase`) y la subida manual
(`UploadDocumentUseCase`). Antes cada uno llegaba al proveedor por su cuenta y
el id se cacheaba en memoria; ahora el id vive en `entities.drive_folder_id`
[055] y esto es lo único que sabe cómo llenarlo.

Está aparte —y no como método de un caso de uso— porque los tres llamadores
son pares: si viviera dentro de uno, los otros dos tendrían que depender de él
por un detalle que no es suyo.
"""

from typing import Optional

from ..domain.ports import IDocumentRepository, IDocumentStorage


async def resolve_entity_folder_id(
    repository: IDocumentRepository,
    storage: IDocumentStorage,
    *,
    entity_id: Optional[str],
    entity_name: Optional[str],
) -> Optional[str]:
    """Id de la carpeta de la sociedad, creándola en Drive solo la primera vez.

    Devuelve `None` cuando la persona no pertenece a ninguna sociedad — el
    externo-invitado — y entonces su carpeta cuelga de la raíz. `None` es una
    respuesta legítima aquí, no un fallo.

    El orden importa: primero la base, y solo si está vacía se pregunta a
    Drive. Es lo que reduce el volcado de 37 consultas por las mismas cuatro
    carpetas a cuatro, y lo que hace que dos peticiones simultáneas vean el
    mismo id en lugar de crear cada una el suyo.
    """
    if entity_id is None or entity_name is None:
        return None

    cached = await repository.find_entity_drive_folder_id(entity_id)
    if cached is not None:
        return cached

    folder_id = await storage.get_or_create_entity_folder(entity_name)
    await repository.save_entity_drive_folder_id(entity_id, folder_id)
    return folder_id
