"""Entidad de dominio del feature `invitations` (gestión del ciclo de vida
de una invitación: listar pendientes, reenviar, cancelar). El alta en sí
(INSERT de la fila) la hace `staff.staff_repository.create_staff_member` en
la misma transacción que `users` — ver docs/design del cambio
`rh-invitaciones-iconos-limpieza`. Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Invitation:
    id: str
    email: str
    # `invitations` no guarda el nombre — se resuelve por JOIN contra
    # `users.email` (la fila ya existe siempre: el alta es EAGER). `None`
    # solo si esa fila desapareciera (no debería pasar hoy).
    full_name: Optional[str]
    role_id: str
    role_code: str
    entity_id: Optional[str]
    entity_code: Optional[str]
    invited_by_name: str
    status: str  # 'pending' | 'accepted' | 'revoked' | 'expired' (CHECK de la tabla)
    expires_at: datetime
    created_at: datetime
