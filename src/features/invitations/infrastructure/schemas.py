"""DTOs de response (Pydantic) del feature `invitations`."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class InvitationDTO(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    role_code: str
    entity_code: Optional[str]
    invited_by_name: str
    status: str
    expires_at: datetime
    created_at: datetime


class InvitationListDTO(BaseModel):
    invitations: list[InvitationDTO]
