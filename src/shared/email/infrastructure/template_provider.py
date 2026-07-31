"""
Adaptador asyncpg de `IEmailTemplateProvider`: lee las plantillas que el admin
haya guardado (`email_templates`, migración 041).

POR QUÉ NO ESTÁ DENTRO DE `render_email`: esa función es pura y su docstring
promete "sin red ni SQL". Esa promesa es lo que permite testear asunto y HTML con
contexto estático, sin Postgres. Este módulo es el que sí toca la BD, y el sender
compone los dos.

UN FALLO AQUÍ NO IMPIDE ENVIAR. Si la consulta revienta —BD caída, tabla sin
migrar, permisos— se registra y se devuelve `None`, que el render interpreta como
"usa el texto por defecto del código". Un correo con el texto de fábrica es
infinitamente mejor que un correo no enviado: el aviso de una ausencia aprobada o
la bienvenida de un alta no pueden depender de que una tabla de personalización
esté disponible.
"""

from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool
from src.shared.logger import get_logger

from ..domain.entities import EmailTemplate

logger = get_logger("shared.email.template_provider")


def _row_to_template(row) -> EmailTemplate:
    return EmailTemplate(
        template_key=row["template_key"],
        label=row["label"],
        description=row["description"],
        subject=row["subject"],
        body=row["body"],
        is_active=row["is_active"],
        updated_by=str(row["updated_by"]) if row["updated_by"] is not None else None,
        updated_at=row["updated_at"],
        audience=row["audience"],
        audience_entity_id=(
            str(row["audience_entity_id"])
            if row["audience_entity_id"] is not None
            else None
        ),
    )


class PostgresEmailTemplateProvider:
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def get(self, template_key: str) -> Optional[EmailTemplate]:
        try:
            row = await self._db.fetchrow(
                """
                SELECT * FROM email_templates
                WHERE template_key = $1 AND is_active = TRUE
                """,
                template_key,
            )
        except Exception as exc:  # noqa: BLE001 — ver el docstring del módulo
            # Deliberadamente ancho: cualquier fallo de lectura degrada al texto
            # por defecto en vez de tumbar el envío. Se loguea a nivel WARNING y
            # no ERROR porque el correo SÍ sale.
            logger.warning(
                "Could not read the email template, falling back to the default text",
                template_key=template_key,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return None

        return _row_to_template(row) if row else None
