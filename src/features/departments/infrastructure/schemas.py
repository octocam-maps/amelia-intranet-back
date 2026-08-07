"""DTOs de response (Pydantic) del feature `departments`."""

from typing import Optional

from pydantic import BaseModel


class DepartmentDTO(BaseModel):
    id: str
    name: str
    entity_id: str
    entity_code: Optional[str]
    # Catálogo 2026 (migración 054): `parent_name` viene resuelto para que el
    # selector pueda agrupar (`<optgroup label="Producto">`) sin tener que
    # cruzar la lista consigo misma buscando el padre por id.
    parent_department_id: Optional[str] = None
    parent_name: Optional[str] = None


class DepartmentListDTO(BaseModel):
    departments: list[DepartmentDTO]
