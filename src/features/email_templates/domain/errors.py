"""Errores de dominio del feature `email_templates`. Heredan de las bases
compartidas para que el `error_handler` global les dé su código HTTP sin
`try/except` en la ruta (mismo patrón que el resto de features)."""

from src.shared.errors.base import NotFoundError, ValidationError


class EmailTemplateNotFoundError(NotFoundError):
    """La `template_key` no está en el catálogo. El catálogo es CERRADO: lo
    siembra la migración 041 con los tipos de correo que el código sabe enviar,
    así que esto es un id inventado, no una plantilla por crear."""


class InvalidEmailTemplateError(ValidationError):
    """Asunto o cuerpo vacíos. Pasan el tipo (`str`) pero no son un correo: uno
    deja la línea en blanco en la bandeja de entrada y el otro un mensaje sin
    texto."""
