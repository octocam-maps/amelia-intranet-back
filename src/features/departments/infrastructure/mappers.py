"""Traduce entidades de dominio (`Department`) a DTOs de FastAPI (Pydantic)."""

from ..domain.entities import Department
from .schemas import DepartmentDTO, DepartmentListDTO


def department_to_dto(department: Department) -> DepartmentDTO:
    return DepartmentDTO(
        id=department.id,
        name=department.name,
        entity_id=department.entity_id,
        entity_code=department.entity_code,
        parent_department_id=department.parent_department_id,
        parent_name=department.parent_name,
    )


def departments_to_dto(departments: list[Department]) -> DepartmentListDTO:
    return DepartmentListDTO(
        departments=[department_to_dto(department) for department in departments]
    )
