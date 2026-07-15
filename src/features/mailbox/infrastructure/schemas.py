"""DTOs de request/response (Pydantic) del feature `mailbox`."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SubmitAnonymousMessageDTO(BaseModel):
    category: Literal["sugerencia", "consulta", "incidencia"]
    body: str = Field(..., min_length=1)
    subject: Optional[str] = None


class SubmitAnonymousMessageResponseDTO(BaseModel):
    reference_code: str


class AnonymousMessageDTO(BaseModel):
    id: str
    reference_code: str
    category: str
    subject: Optional[str]
    body: str
    status: str
    admin_reply: Optional[str]
    created_at: datetime


class AnonymousMessageListDTO(BaseModel):
    messages: list[AnonymousMessageDTO]


class ReplyToMessageDTO(BaseModel):
    admin_reply: str = Field(..., min_length=1)


class TrackMessageDTO(BaseModel):
    reference_code: str
    category: str
    subject: Optional[str]
    body: str
    status: str
    admin_reply: Optional[str]
    created_at: datetime
