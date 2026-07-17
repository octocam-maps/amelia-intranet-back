"""
Router de `/mailbox`: buzón anónimo. El anonimato es estructural — el POST
de envío exige rol (solo para frenar spam) pero NO lee ni registra la IP
del request (docs/fase-0-esquema-datos.md § buzón anónimo). `/track/...`
es intencionalmente público: es el único canal que tiene el emisor anónimo
para ver la respuesta, así que exigirle un token lo identificaría.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from src.shared.auth.dependencies import require_role
from src.shared.middleware import limiter

from ..application.use_cases.list_mailbox_messages import ListMailboxMessagesUseCase
from ..application.use_cases.reply_to_message import ReplyToMailboxMessageUseCase
from ..application.use_cases.resolve_message import ResolveMailboxMessageUseCase
from ..application.use_cases.submit_anonymous_message import SubmitAnonymousMessageUseCase
from ..application.use_cases.track_message import TrackMailboxMessageUseCase
from .dependencies import (
    get_list_mailbox_messages_use_case,
    get_reply_to_message_use_case,
    get_resolve_message_use_case,
    get_submit_anonymous_message_use_case,
    get_track_message_use_case,
)
from .mappers import message_to_dto, message_to_track_dto, messages_to_dto
from .schemas import (
    AnonymousMessageDTO,
    AnonymousMessageListDTO,
    ReplyToMessageDTO,
    SubmitAnonymousMessageDTO,
    SubmitAnonymousMessageResponseDTO,
    TrackMessageDTO,
)


def create_mailbox_router() -> APIRouter:
    router = APIRouter(prefix="/mailbox", tags=["mailbox"])

    @router.post("/messages", response_model=SubmitAnonymousMessageResponseDTO, status_code=201)
    @limiter.limit("10/minute")
    async def submit_message(
        dto: SubmitAnonymousMessageDTO,
        request: Request,
        # El rol solo gatea spam (exige una sesión válida) — a partir de
        # aquí ni el handler ni el caso de uso ni el repositorio vuelven a
        # tocar `current_user`. No propagarlo a la capa de aplicación es
        # intencional (docs/permisos-roles.md § Buzón anónimo). `socio`
        # [migración 024] puede enviar igual que cualquier empleado — sigue
        # sin acceso a la recepción (`GET/POST /messages/*` más abajo).
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
        use_case: SubmitAnonymousMessageUseCase = Depends(get_submit_anonymous_message_use_case),
    ):
        message = await use_case.execute(category=dto.category, subject=dto.subject, body=dto.body)
        return SubmitAnonymousMessageResponseDTO(reference_code=message.reference_code)

    @router.get("/messages", response_model=AnonymousMessageListDTO)
    async def list_messages(
        status: Optional[str] = Query(
            None, pattern="^(unread|all|resolved)$", description="unread|all|resolved"
        ),
        current_user: dict = Depends(require_role("administrador")),
        use_case: ListMailboxMessagesUseCase = Depends(get_list_mailbox_messages_use_case),
    ):
        """Recepción del buzón — exclusiva del admin (docs/permisos-roles.md § Buzón anónimo)."""
        messages = await use_case.execute(status_filter=status)
        return messages_to_dto(messages)

    @router.post("/messages/{message_id}/reply", response_model=AnonymousMessageDTO)
    async def reply_to_message(
        message_id: str,
        dto: ReplyToMessageDTO,
        current_user: dict = Depends(require_role("administrador")),
        use_case: ReplyToMailboxMessageUseCase = Depends(get_reply_to_message_use_case),
    ):
        """La respuesta queda en el propio mensaje — el emisor la ve por su
        `reference_code` (`GET /mailbox/track/...`), nunca se vincula a un
        user_id ni se envía por un canal que revele su identidad."""
        message = await use_case.execute(message_id=message_id, admin_reply=dto.admin_reply)
        return message_to_dto(message)

    @router.post("/messages/{message_id}/resolve", response_model=AnonymousMessageDTO)
    async def resolve_message(
        message_id: str,
        current_user: dict = Depends(require_role("administrador")),
        use_case: ResolveMailboxMessageUseCase = Depends(get_resolve_message_use_case),
    ):
        message = await use_case.execute(message_id=message_id)
        return message_to_dto(message)

    @router.get("/track/{reference_code}", response_model=TrackMessageDTO)
    @limiter.limit("20/minute")
    async def track_message(
        reference_code: str,
        request: Request,
        use_case: TrackMailboxMessageUseCase = Depends(get_track_message_use_case),
    ):
        """Sin auth por diseño: el `reference_code` ES la credencial de
        seguimiento anónimo — exigir un token aquí rompería el anonimato al
        atar el seguimiento a una identidad."""
        message = await use_case.execute(reference_code=reference_code)
        return message_to_track_dto(message)

    return router
