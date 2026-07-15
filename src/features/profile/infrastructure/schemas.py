"""DTOs de response (Pydantic) del feature `profile`."""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class ProfileDTO(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str]
    role: str
    job_title: Optional[str]
    hire_date: Optional[date]
    entity_name: Optional[str]
    department_name: Optional[str]
    manager_name: Optional[str]
    is_external: bool
