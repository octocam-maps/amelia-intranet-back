"""DTOs de request/response (Pydantic) del feature `notifications`."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class NotificationDTO(BaseModel):
    id: str
    type: str
    title: str
    body: Optional[str]
    data: dict[str, Any]
    read: bool
    created_at: datetime


class NotificationListDTO(BaseModel):
    items: list[NotificationDTO]
    next_before: Optional[datetime]


class UnreadCountDTO(BaseModel):
    count: int


class MarkAllReadResponseDTO(BaseModel):
    updated: int


class RunNotificationJobResponseDTO(BaseModel):
    job: str
    result: dict[str, Any]
