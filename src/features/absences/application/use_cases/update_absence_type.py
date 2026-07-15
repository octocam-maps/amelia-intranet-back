"""Caso de uso: editar / activar-desactivar un tipo de ausencia. `code` no
es editable (ver nota en el puerto). Desactivar (`is_active=False`) es el
único "borrado" que existe para este recurso: `absence_requests.absence_type_id`
usa `ON DELETE RESTRICT`, así que un tipo con solicitudes asociadas no se
puede eliminar físicamente sin romper el histórico — no se expone ningún
endpoint de DELETE."""

from typing import Optional

from ...domain.entities import AbsenceType
from ...domain.errors import AbsenceTypeNotFoundError
from ...domain.ports import IAbsenceRepository


class UpdateAbsenceTypeUseCase:
    def __init__(self, repository: IAbsenceRepository):
        self._repository = repository

    async def execute(
        self,
        absence_type_id: str,
        *,
        name: Optional[str] = None,
        is_paid: Optional[bool] = None,
        affects_balance: Optional[bool] = None,
        default_entitled_days: Optional[float] = None,
        color: Optional[str] = None,
        is_active: Optional[bool] = None,
        requires_approval: Optional[bool] = None,
        requires_justification: Optional[bool] = None,
        max_days_per_year: Optional[int] = None,
    ) -> AbsenceType:
        updated = await self._repository.update_type(
            absence_type_id,
            name=name,
            is_paid=is_paid,
            affects_balance=affects_balance,
            default_entitled_days=default_entitled_days,
            color=color,
            is_active=is_active,
            requires_approval=requires_approval,
            requires_justification=requires_justification,
            max_days_per_year=max_days_per_year,
        )
        if updated is None:
            raise AbsenceTypeNotFoundError("El tipo de ausencia no existe.")
        return updated
