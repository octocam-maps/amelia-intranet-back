"""
Router de `/onboarding`: catálogo + progreso propio, y las 5 acciones de
paso (vídeo, cuestionario, firma, manual, perfil). El externo-invitado tiene
onboarding parcial (vídeo + manual) — se le deja pasar el `require_role` de
los endpoints comunes, pero el caso de uso rechaza en el backend si intenta
operar sobre quiz/firma/perfil (`StepNotAvailableForRoleError`, 403). Los
endpoints exclusivos de internos (`quiz`, `sign`, `complete-profile`)
además cortan antes, en el propio `require_role` — defensa en profundidad,
no solo un ítem oculto del navbar.
"""

from fastapi import APIRouter, Depends, Request

from src.shared.auth.dependencies import require_role
from src.shared.utils.client_ip import get_client_ip

from ..application.use_cases.acknowledge_manual import AcknowledgeManualUseCase
from ..application.use_cases.complete_profile import CompleteProfileUseCase
from ..application.use_cases.get_my_onboarding import GetMyOnboardingUseCase
from ..application.use_cases.sign_document import SignDocumentUseCase
from ..application.use_cases.submit_quiz import SubmitQuizUseCase
from ..application.use_cases.update_video_progress import UpdateVideoProgressUseCase
from .dependencies import (
    get_acknowledge_manual_use_case,
    get_complete_profile_use_case,
    get_my_onboarding_use_case,
    get_sign_document_use_case,
    get_submit_quiz_use_case,
    get_update_video_progress_use_case,
)
from .mappers import (
    acknowledgement_to_dto,
    progress_to_dto,
    quiz_attempt_to_dto,
    signature_to_dto,
    steps_with_progress_to_dto,
)
from .schemas import (
    AcknowledgementDTO,
    CompleteProfileRequestDTO,
    OnboardingMeDTO,
    OnboardingProgressDTO,
    QuizResultDTO,
    QuizSubmitRequestDTO,
    SignatureDTO,
    VideoProgressRequestDTO,
)

_ALL_ROLES = ("administrador", "empleado", "externo_invitado")
_INTERNAL_ONLY = ("administrador", "empleado")


def create_onboarding_router() -> APIRouter:
    router = APIRouter(prefix="/onboarding", tags=["onboarding"])

    @router.get("/me", response_model=OnboardingMeDTO)
    async def get_my_onboarding(
        current_user: dict = Depends(require_role(*_ALL_ROLES)),
        use_case: GetMyOnboardingUseCase = Depends(get_my_onboarding_use_case),
    ):
        """Pasos aplicables al rol del usuario, con progreso y desbloqueo ya
        calculados. Inicializa el progreso en la primera visita."""
        pairs = await use_case.execute(
            user_id=current_user["sub"], role=current_user["role"]
        )
        return steps_with_progress_to_dto(pairs)

    @router.post(
        "/steps/{step_id}/video-progress", response_model=OnboardingProgressDTO
    )
    async def report_video_progress(
        step_id: str,
        dto: VideoProgressRequestDTO,
        current_user: dict = Depends(require_role(*_ALL_ROLES)),
        use_case: UpdateVideoProgressUseCase = Depends(
            get_update_video_progress_use_case
        ),
    ):
        """Solo acepta progreso monotónico creciente y con saltos
        razonables — rechaza un intento de saltar el vídeo (p.ej. 0 -> 100
        de golpe)."""
        progress = await use_case.execute(
            user_id=current_user["sub"],
            role=current_user["role"],
            step_id=step_id,
            new_pct=dto.progress_pct,
        )
        return progress_to_dto(progress)

    @router.post("/steps/{step_id}/quiz", response_model=QuizResultDTO)
    async def submit_quiz(
        step_id: str,
        dto: QuizSubmitRequestDTO,
        current_user: dict = Depends(require_role(*_INTERNAL_ONLY)),
        use_case: SubmitQuizUseCase = Depends(get_submit_quiz_use_case),
    ):
        """Intento único (UNIQUE en BD) — un segundo intento se rechaza sin
        exponer nunca la respuesta correcta."""
        attempt = await use_case.execute(
            user_id=current_user["sub"],
            role=current_user["role"],
            step_id=step_id,
            answers=dto.answers,
        )
        return quiz_attempt_to_dto(attempt)

    @router.post("/steps/{step_id}/sign", response_model=SignatureDTO)
    async def sign_document(
        step_id: str,
        request: Request,
        current_user: dict = Depends(require_role(*_INTERNAL_ONLY)),
        use_case: SignDocumentUseCase = Depends(get_sign_document_use_case),
    ):
        """Firma digital trazable: fecha/hora, IP y hash del documento
        (regla no negociable §7)."""
        signature = await use_case.execute(
            user_id=current_user["sub"],
            role=current_user["role"],
            step_id=step_id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        return signature_to_dto(signature, step_id)

    @router.post("/steps/{step_id}/acknowledge", response_model=AcknowledgementDTO)
    async def acknowledge_manual(
        step_id: str,
        request: Request,
        current_user: dict = Depends(require_role(*_ALL_ROLES)),
        use_case: AcknowledgeManualUseCase = Depends(get_acknowledge_manual_use_case),
    ):
        """Confirmación de lectura del manual — abierto también al
        externo-invitado (docs/permisos-roles.md § Onboarding parcial)."""
        acknowledgement = await use_case.execute(
            user_id=current_user["sub"],
            role=current_user["role"],
            step_id=step_id,
            ip_address=get_client_ip(request),
        )
        return acknowledgement_to_dto(acknowledgement, step_id)

    @router.post(
        "/steps/{step_id}/complete-profile", response_model=OnboardingProgressDTO
    )
    async def complete_profile(
        step_id: str,
        dto: CompleteProfileRequestDTO,
        current_user: dict = Depends(require_role(*_INTERNAL_ONLY)),
        use_case: CompleteProfileUseCase = Depends(get_complete_profile_use_case),
    ):
        """Borrador: acepta un payload básico — el esquema real del perfil
        llega con la Fase 3."""
        progress = await use_case.execute(
            user_id=current_user["sub"],
            role=current_user["role"],
            step_id=step_id,
            data=dto.model_dump(exclude_none=True),
        )
        return progress_to_dto(progress)

    return router
