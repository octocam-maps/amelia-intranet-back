"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.features.auth.infrastructure.repositories.session_repository import (
    PostgresSessionRepository,
)
from src.shared.config import get_settings
from src.shared.database import get_database_pool
from src.shared.email import get_email_sender

from ..application.use_cases.create_staff_member import CreateStaffMemberUseCase
from ..application.use_cases.list_staff import ListStaffUseCase
from ..application.use_cases.update_staff_member import UpdateStaffMemberUseCase
from .repositories.staff_repository import PostgresStaffRepository


def _get_repository() -> PostgresStaffRepository:
    return PostgresStaffRepository(get_database_pool())


def _get_session_revoker() -> PostgresSessionRepository:
    # Reutiliza el adaptador del feature `auth` (mismo patrón que
    # `documents/infrastructure/dependencies.py` reutilizando
    # `PostgresStaffRepository`) — `staff.domain` no lo conoce, solo define
    # el puerto (`ISessionRevoker`) que esta clase cumple por estructura.
    return PostgresSessionRepository(get_database_pool())


def get_list_staff_use_case() -> ListStaffUseCase:
    return ListStaffUseCase(_get_repository())


def get_create_staff_member_use_case() -> CreateStaffMemberUseCase:
    settings = get_settings()
    return CreateStaffMemberUseCase(
        _get_repository(),
        get_email_sender(),
        settings.invitation_expires_days,
        settings.frontend_url,
    )


def get_update_staff_member_use_case() -> UpdateStaffMemberUseCase:
    return UpdateStaffMemberUseCase(_get_repository(), _get_session_revoker())
