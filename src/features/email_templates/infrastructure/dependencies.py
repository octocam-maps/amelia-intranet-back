"""Wiring de FastAPI del feature `email_templates`."""

from src.shared.config import get_settings
from src.shared.database import get_database_pool

from ..application.use_cases.manage_email_templates import (
    ListEmailTemplatesUseCase,
    PreviewEmailTemplateUseCase,
    RestoreEmailTemplateUseCase,
    UpdateEmailTemplateUseCase,
)
from .repositories.email_template_repository import PostgresEmailTemplateRepository


def _get_repository() -> PostgresEmailTemplateRepository:
    return PostgresEmailTemplateRepository(get_database_pool())


def get_list_email_templates_use_case() -> ListEmailTemplatesUseCase:
    return ListEmailTemplatesUseCase(_get_repository())


def get_update_email_template_use_case() -> UpdateEmailTemplateUseCase:
    return UpdateEmailTemplateUseCase(_get_repository())


def get_restore_email_template_use_case() -> RestoreEmailTemplateUseCase:
    return RestoreEmailTemplateUseCase(_get_repository())


def get_preview_email_template_use_case() -> PreviewEmailTemplateUseCase:
    return PreviewEmailTemplateUseCase(
        _get_repository(), frontend_url=get_settings().frontend_url
    )
