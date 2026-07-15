"""Caso de uso: crear un tipo de ausencia (exclusivo del admin,
docs/permisos-roles.md § "Tipos de ausencia": "Crear / editar tipos")."""

from typing import Optional

from ...domain.entities import AbsenceType
from ...domain.errors import AbsenceTypeCodeAlreadyExistsError
from ...domain.ports import IAbsenceRepository


class CreateAbsenceTypeUseCase:
    def __init__(self, repository: IAbsenceRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        code: str,
        name: str,
        is_paid: bool,
        affects_balance: bool,
        default_entitled_days: float,
        color: Optional[str],
        requires_approval: bool = True,
        requires_justification: bool = False,
        max_days_per_year: Optional[int] = None,
    ) -> AbsenceType:
        normalized_code = code.strip().lower()
        if await self._repository.find_type_by_code(normalized_code) is not None:
            raise AbsenceTypeCodeAlreadyExistsError(
                f"Ya existe un tipo de ausencia con el código '{normalized_code}'."
            )

        return await self._repository.create_type(
            code=normalized_code,
            name=name,
            is_paid=is_paid,
            affects_balance=affects_balance,
            default_entitled_days=default_entitled_days,
            color=color,
            requires_approval=requires_approval,
            requires_justification=requires_justification,
            max_days_per_year=max_days_per_year,
        )
