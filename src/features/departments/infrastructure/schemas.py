"""DTOs de response (Pydantic) del feature `departments`."""

from typing import Optional

from pydantic import BaseModel


class DepartmentDTO(BaseModel):
    id: str
    name: str
    entity_id: str
    entity_code: Optional[str]


class DepartmentListDTO(BaseModel):
    departments: list[DepartmentDTO]
