"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.features.notifications.infrastructure.dependencies import get_notify_use_case
from src.shared.database import get_database_pool

from ..application.use_cases.acknowledge_manual import AcknowledgeManualUseCase
from ..application.use_cases.complete_profile import CompleteProfileUseCase
from ..application.use_cases.get_my_onboarding import GetMyOnboardingUseCase
from ..application.use_cases.get_onboarding_progress_overview import (
    GetOnboardingProgressOverviewUseCase,
)
from ..application.use_cases.list_onboarding_steps_admin import (
    ListOnboardingStepsForAdminUseCase,
)
from ..application.use_cases.reset_quiz_attempt import ResetQuizAttemptUseCase
from ..application.use_cases.sign_document import SignDocumentUseCase
from ..application.use_cases.submit_quiz import SubmitQuizUseCase
from ..application.use_cases.update_onboarding_step import UpdateOnboardingStepUseCase
from ..application.use_cases.update_video_progress import UpdateVideoProgressUseCase
from .repositories.onboarding_repository import PostgresOnboardingRepository


def _get_repository() -> PostgresOnboardingRepository:
    return PostgresOnboardingRepository(get_database_pool())


def get_my_onboarding_use_case() -> GetMyOnboardingUseCase:
    return GetMyOnboardingUseCase(_get_repository(), get_notify_use_case())


def get_update_video_progress_use_case() -> UpdateVideoProgressUseCase:
    return UpdateVideoProgressUseCase(_get_repository())


def get_submit_quiz_use_case() -> SubmitQuizUseCase:
    return SubmitQuizUseCase(_get_repository())


def get_sign_document_use_case() -> SignDocumentUseCase:
    return SignDocumentUseCase(_get_repository())


def get_acknowledge_manual_use_case() -> AcknowledgeManualUseCase:
    return AcknowledgeManualUseCase(_get_repository())


def get_complete_profile_use_case() -> CompleteProfileUseCase:
    return CompleteProfileUseCase(_get_repository(), get_notify_use_case())


def get_list_onboarding_steps_admin_use_case() -> ListOnboardingStepsForAdminUseCase:
    return ListOnboardingStepsForAdminUseCase(_get_repository())


def get_update_onboarding_step_use_case() -> UpdateOnboardingStepUseCase:
    return UpdateOnboardingStepUseCase(_get_repository())


def get_onboarding_progress_overview_use_case() -> GetOnboardingProgressOverviewUseCase:
    return GetOnboardingProgressOverviewUseCase(_get_repository())


def get_reset_quiz_attempt_use_case() -> ResetQuizAttemptUseCase:
    return ResetQuizAttemptUseCase(_get_repository())
