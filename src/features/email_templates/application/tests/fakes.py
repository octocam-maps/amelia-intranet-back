"""Fake en memoria de `IEmailTemplateRepository` — mismo patrón que el resto de
features (`staff`, `onboarding`)."""

from datetime import datetime, timezone
from typing import Optional

from src.shared.email.domain.entities import EmailTemplate


def build_template(**overrides) -> EmailTemplate:
    defaults = {
        "template_key": "staff_invited",
        "label": "Bienvenida al dar de alta",
        "description": "Se envía a la persona recién dada de alta.",
        "subject": "Te damos la bienvenida a la intranet de Amelia",
        "body": "Hola {{full_name}},",
        "is_active": True,
        "updated_by": None,
        "updated_at": None,
    }
    return EmailTemplate(**{**defaults, **overrides})


class FakeEmailTemplateRepository:
    def __init__(self, templates: Optional[list[EmailTemplate]] = None):
        self.templates: dict[str, EmailTemplate] = {
            t.template_key: t for t in (templates or [build_template()])
        }

    async def list_templates(self) -> list[EmailTemplate]:
        return sorted(self.templates.values(), key=lambda t: t.label)

    async def find_by_key(self, template_key: str) -> Optional[EmailTemplate]:
        return self.templates.get(template_key)

    async def update_template(
        self, template_key, *, subject, body, updated_by
    ) -> Optional[EmailTemplate]:
        existing = self.templates.get(template_key)
        if existing is None:
            return None
        # Igual que el repositorio real: guardar REACTIVA la plantilla.
        updated = EmailTemplate(
            template_key=existing.template_key,
            label=existing.label,
            description=existing.description,
            subject=subject,
            body=body,
            is_active=True,
            updated_by=updated_by,
            updated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        )
        self.templates[template_key] = updated
        return updated

    async def deactivate_template(
        self, template_key, *, updated_by
    ) -> Optional[EmailTemplate]:
        existing = self.templates.get(template_key)
        if existing is None:
            return None
        # NO borra: conserva `subject`/`body` para que el admin pueda volver.
        restored = EmailTemplate(
            template_key=existing.template_key,
            label=existing.label,
            description=existing.description,
            subject=existing.subject,
            body=existing.body,
            is_active=False,
            updated_by=updated_by,
            updated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        )
        self.templates[template_key] = restored
        return restored
