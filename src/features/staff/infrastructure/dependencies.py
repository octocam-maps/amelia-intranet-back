"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.features.auth.infrastructure.repositories.session_repository import (
    PostgresSessionRepository,
)
from src.features.documents.application.use_cases.provision_employee_drive_folder import (
    ProvisionEmployeeDriveFolderUseCase,
)
from src.features.documents.infrastructure.factory import get_document_storage
from src.features.documents.infrastructure.repositories.document_repository import (
    PostgresDocumentRepository,
)
from src.shared.config import get_settings
from src.shared.database import get_database_pool
from src.shared.email import get_email_sender

from ..application.use_cases.create_staff_member import CreateStaffMemberUseCase
from ..application.use_cases.list_staff import ListStaffUseCase
from ..application.use_cases.update_staff_member import UpdateStaffMemberUseCase
from ..domain.ports import IDriveFolderProvisioner
from .repositories.staff_repository import PostgresStaffRepository


def _get_repository() -> PostgresStaffRepository:
    return PostgresStaffRepository(get_database_pool())


def _get_session_revoker() -> PostgresSessionRepository:
    # Reutiliza el adaptador del feature `auth` (mismo patrón que
    # `documents/infrastructure/dependencies.py` reutilizando
    # `PostgresStaffRepository`) — `staff.domain` no lo conoce, solo define
    # el puerto (`ISessionRevoker`) que esta clase cumple por estructura.
    return PostgresSessionRepository(get_database_pool())


class _DriveFolderProvisionerAdapter:
    """Adapta `ProvisionEmployeeDriveFolderUseCase` (feature `documents`) al
    puerto `IDriveFolderProvisioner` que consume `staff.application` — mismo
    patrón de recomposición entre features que `_get_session_revoker`."""

    def __init__(self, use_case: ProvisionEmployeeDriveFolderUseCase):
        self._use_case = use_case

    async def provision_folder(self, user_id: str, email: str) -> None:
        await self._use_case.execute(user_id=user_id, email=email)


def _get_drive_folder_provisioner() -> IDriveFolderProvisioner:
    use_case = ProvisionEmployeeDriveFolderUseCase(
        PostgresDocumentRepository(get_database_pool()), get_document_storage()
    )
    return _DriveFolderProvisionerAdapter(use_case)


def get_list_staff_use_case() -> ListStaffUseCase:
    return ListStaffUseCase(_get_repository())


def get_create_staff_member_use_case() -> CreateStaffMemberUseCase:
    settings = get_settings()
    return CreateStaffMemberUseCase(
        _get_repository(),
        get_email_sender(),
        settings.invitation_expires_days,
        settings.frontend_url,
        _get_drive_folder_provisioner(),
    )


def get_update_staff_member_use_case() -> UpdateStaffMemberUseCase:
    return UpdateStaffMemberUseCase(_get_repository(), _get_session_revoker())
