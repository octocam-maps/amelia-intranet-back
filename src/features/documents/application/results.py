"""Resultados compuestos de casos de uso del feature `documents` que
necesitan devolver algo más que una entidad de dominio pura — mismo patrón
que `auth.application.results`."""

from dataclasses import dataclass

from ..domain.models import Document


@dataclass(frozen=True)
class DocumentDownload:
    """Resultado de `DownloadDocumentUseCase`: metadatos del documento
    (nombre/`mime_type` para el `Content-Disposition`, WU-C2) + el binario
    ya descargado desde el proveedor de almacenamiento activo."""

    document: Document
    content: bytes
