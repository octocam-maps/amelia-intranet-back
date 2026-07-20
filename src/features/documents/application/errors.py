"""
Errores de aplicación del feature `documents`. Heredan de las clases base
de `src.shared.errors.base` — mismo patrón que `absences.domain.errors`
(las rutas de WU-C2 los traducen a códigos HTTP)."""

from src.shared.errors.base import (
    InsufficientPermissionsError,
    NotFoundError,
    ValidationError,
)


class DocumentNotFoundError(NotFoundError):
    """No existe un documento con ese id, o ya está borrado (`deleted_at`)."""


class DocumentOwnerNotFoundError(NotFoundError):
    """El `user_id` indicado por el admin al subir un documento no
    corresponde a ningún miembro de la plantilla (`IStaffRepository.find_by_id`)."""


class DocumentForbiddenError(InsufficientPermissionsError):
    """Un empleado o socio intenta leer/descargar un documento de otro
    usuario — alcance RGPD: cada uno solo accede a lo suyo
    (docs/permisos-roles.md)."""


class InvalidDocumentCategoryError(ValidationError):
    """`category` no está en `DOCUMENT_CATEGORIES` (CHECK de
    `employee_documents`, `004_documents.sql`)."""


class InvalidDocumentMimeTypeError(ValidationError):
    """El archivo subido no es `application/pdf` — única extensión
    admitida por la subida manual (mismo criterio que aplicará el sync, WU-D)."""


class DocumentTooLargeError(ValidationError):
    """El archivo supera `DOCUMENTS_MAX_UPLOAD_MB`."""
