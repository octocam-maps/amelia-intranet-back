"""
Puerto del feature `email_templates` (pantalla de administración de los textos de
los correos automáticos, migración 041).

`domain` no importa nada de `infrastructure` ni de FastAPI. La ENTIDAD se
reutiliza de `shared/email/domain/entities.py` (`EmailTemplate`) en vez de
duplicarla aquí: es la misma fila que lee el sender al enviar, y dos definiciones
del mismo concepto habrían divergido en el primer campo que se añadiera.
"""

from typing import Optional, Protocol

from src.shared.email.domain.entities import EmailTemplate


class IEmailTemplateRepository(Protocol):
    async def list_templates(self) -> list[EmailTemplate]:
        """Todas las plantillas del catálogo, activas o no, en orden estable para
        la pantalla. Incluye las desactivadas: son las que están "usando el texto
        por defecto", y el admin tiene que verlas para poder reactivarlas."""
        ...

    async def find_by_key(self, template_key: str) -> Optional[EmailTemplate]:
        ...

    async def update_template(
        self,
        template_key: str,
        *,
        subject: str,
        body_html: str,
        updated_by: Optional[str],
    ) -> Optional[EmailTemplate]:
        """Guarda el texto del admin y REACTIVA la plantilla: editar es querer
        usar lo editado. `None` si la clave no existe (el catálogo es cerrado —
        lo siembra la migración, no se crean plantillas desde la UI)."""
        ...

    async def deactivate_template(
        self, template_key: str, *, updated_by: Optional[str]
    ) -> Optional[EmailTemplate]:
        """El botón «Restaurar el texto por defecto»: desactiva en vez de borrar,
        así lo que el admin había escrito se conserva por si quiere volver."""
        ...
