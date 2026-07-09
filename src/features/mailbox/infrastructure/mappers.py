from ..domain.entities import AnonymousMessage
from .schemas import AnonymousMessageDTO, AnonymousMessageListDTO, TrackMessageDTO


def message_to_dto(message: AnonymousMessage) -> AnonymousMessageDTO:
    return AnonymousMessageDTO(
        id=message.id,
        reference_code=message.reference_code,
        category=message.category,
        subject=message.subject,
        body=message.body,
        status=message.status,
        admin_reply=message.admin_reply,
        created_at=message.created_at,
    )


def messages_to_dto(messages: list[AnonymousMessage]) -> AnonymousMessageListDTO:
    return AnonymousMessageListDTO(messages=[message_to_dto(m) for m in messages])


def message_to_track_dto(message: AnonymousMessage) -> TrackMessageDTO:
    return TrackMessageDTO(
        reference_code=message.reference_code,
        category=message.category,
        subject=message.subject,
        body=message.body,
        status=message.status,
        admin_reply=message.admin_reply,
        created_at=message.created_at,
    )
