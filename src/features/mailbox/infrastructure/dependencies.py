"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.shared.database import get_database_pool

from ..application.use_cases.list_mailbox_messages import ListMailboxMessagesUseCase
from ..application.use_cases.reply_to_message import ReplyToMailboxMessageUseCase
from ..application.use_cases.resolve_message import ResolveMailboxMessageUseCase
from ..application.use_cases.submit_anonymous_message import SubmitAnonymousMessageUseCase
from ..application.use_cases.track_message import TrackMailboxMessageUseCase
from .repositories.mailbox_repository import PostgresMailboxRepository


def _get_repository() -> PostgresMailboxRepository:
    return PostgresMailboxRepository(get_database_pool())


def get_submit_anonymous_message_use_case() -> SubmitAnonymousMessageUseCase:
    return SubmitAnonymousMessageUseCase(_get_repository())


def get_list_mailbox_messages_use_case() -> ListMailboxMessagesUseCase:
    return ListMailboxMessagesUseCase(_get_repository())


def get_reply_to_message_use_case() -> ReplyToMailboxMessageUseCase:
    return ReplyToMailboxMessageUseCase(_get_repository())


def get_resolve_message_use_case() -> ResolveMailboxMessageUseCase:
    return ResolveMailboxMessageUseCase(_get_repository())


def get_track_message_use_case() -> TrackMailboxMessageUseCase:
    return TrackMailboxMessageUseCase(_get_repository())
