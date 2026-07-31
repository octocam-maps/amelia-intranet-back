"""
Adaptador asyncpg de `IEmailTemplateRepository`. SQL crudo — sin ORM.

Este es el lado de ESCRITURA de `email_templates` (la pantalla de administración).
El de lectura durante el envío es
`shared/email/infrastructure/template_provider.py`, que es distinto a propósito:
allí un fallo se degrada a "usa el texto por defecto" para no tumbar un correo,
y aquí un fallo debe salir a la superficie — si el admin guarda un cambio y no se
persiste, tiene que enterarse.
"""

from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool
from src.shared.email.domain.entities import EmailTemplate

_SELECT = """
    SELECT template_key, label, description, subject, body_html, is_active,
           updated_by, updated_at, audience, audience_entity_id
    FROM email_templates
"""

_RETURNING = """
    RETURNING template_key, label, description, subject, body_html, is_active,
              updated_by, updated_at, audience, audience_entity_id
"""


def _row_to_template(row) -> EmailTemplate:
    return EmailTemplate(
        template_key=row["template_key"],
        label=row["label"],
        description=row["description"],
        subject=row["subject"],
        body_html=row["body_html"],
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


class PostgresEmailTemplateRepository:
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_templates(self) -> list[EmailTemplate]:
        # Orden por `label` y no por `template_key`: el admin busca "Bienvenida",
        # no `staff_invited`.
        #
        # SIN `COLLATE "es_ES"`: esa colación no existe en todas las instalaciones
        # de Postgres y habría sido un 500 en la primera carga de la pantalla en
        # cualquier entorno que no la tuviera. Con 15 filas el orden lo puede
        # afinar el cliente si algún día hace falta; lo que no puede es
        # recuperarse de un error de la query.
        rows = await self._db.fetch(f"{_SELECT} ORDER BY label ASC")
        return [_row_to_template(row) for row in rows]

    async def find_by_key(self, template_key: str) -> Optional[EmailTemplate]:
        row = await self._db.fetchrow(
            f"{_SELECT} WHERE template_key = $1", template_key
        )
        return _row_to_template(row) if row else None

    async def update_template(
        self,
        template_key: str,
        *,
        subject: str,
        body_html: str,
        updated_by: Optional[str],
        audience: Optional[str] = None,
        audience_entity_id: Optional[str] = None,
    ) -> Optional[EmailTemplate]:
        # `is_active = TRUE` en el UPDATE: editar una plantilla que estaba
        # restaurada al texto por defecto es querer volver a usar la personalizada.
        # Sin esto, el admin guardaría un cambio y no vería ningún efecto.
        #
        # `audience` con `COALESCE`: solo lo mandan las plantillas de fan-out, así
        # que un `None` significa "no lo toques" y no "bórralo". `audience_entity_id`
        # NO usa COALESCE porque pasar de `entity` a `all` tiene que poder limpiar
        # la entidad — si no, quedaría una referencia huérfana que el CHECK ya no
        # vigila.
        row = await self._db.fetchrow(
            f"""
            UPDATE email_templates
            SET subject = $2,
                body_html = $3,
                is_active = TRUE,
                updated_by = $4,
                audience = COALESCE($5, audience),
                audience_entity_id = CASE
                    WHEN $5 IS NULL THEN audience_entity_id
                    ELSE $6
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE template_key = $1
            {_RETURNING}
            """,
            template_key,
            subject,
            body_html,
            updated_by,
            audience,
            audience_entity_id,
        )
        return _row_to_template(row) if row else None

    async def deactivate_template(
        self, template_key: str, *, updated_by: Optional[str]
    ) -> Optional[EmailTemplate]:
        # NO borra la fila: el texto que el admin había escrito se conserva por si
        # quiere volver a él, y el catálogo (label/description) lo siembra la
        # migración y no se puede recrear desde la UI.
        row = await self._db.fetchrow(
            """
            UPDATE email_templates
            SET is_active = FALSE,
                updated_by = $2,
                updated_at = CURRENT_TIMESTAMP
            WHERE template_key = $1
            {_RETURNING}
            """.format(_RETURNING=_RETURNING),
            template_key,
            updated_by,
        )
        return _row_to_template(row) if row else None
