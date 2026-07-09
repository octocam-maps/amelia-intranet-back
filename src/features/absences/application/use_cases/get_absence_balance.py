"""
Caso de uso: consultar el saldo (contador en tiempo real) de un usuario para
el año en curso, por cada tipo de ausencia configurado.
"""

from typing import Optional

from src.shared.utils.timezone import today_in_madrid

from ...domain.entities import AbsenceBalance
from ...domain.errors import AbsenceForbiddenError
from ...domain.ports import IAbsenceRepository


class GetAbsenceBalanceUseCase:
    def __init__(self, repository: IAbsenceRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        requester_id: str,
        requester_role: str,
        target_user_id: Optional[str] = None,
        year: Optional[int] = None,
    ) -> list[AbsenceBalance]:
        effective_user_id = requester_id
        if target_user_id is not None and target_user_id != requester_id:
            if requester_role != "administrador":
                raise AbsenceForbiddenError("No puedes ver el saldo de otro usuario.")
            effective_user_id = target_user_id

        resolved_year = year or today_in_madrid().year  # TZ-1: año en Europe/Madrid, no UTC

        # Asegura que TODOS los tipos configurados tengan fila de saldo,
        # aunque el usuario nunca haya solicitado ese tipo todavía — así el
        # frontend siempre puede pintar el contador en cero en vez de "sin datos".
        types = await self._repository.list_types()
        for absence_type in types:
            await self._repository.get_or_create_balance(
                effective_user_id, absence_type.id, resolved_year
            )

        return await self._repository.list_balances_for_user(effective_user_id, resolved_year)
