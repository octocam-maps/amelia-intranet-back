"""Caso de uso: alta de una persona en la plantilla
(docs/deck-fase6/10-editar-persona.png — mismo modal para alta y edición).
Crea el usuario con `status='invited'`: transiciona a `active` en su
primer login con Google, igual que cualquier alta existente
(007_seed_initial_admin.sql)."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from src.shared.auth.roles import RoleCode
from src.shared.email.domain.ports import IEmailSender
from src.shared.logger import get_logger

from ...domain.entities import StaffMember
from ...domain.errors import (
    InvalidEntityCodeError,
    InvalidRoleCodeError,
    StaffEmailAlreadyExistsError,
)
from ...domain.ports import IDriveFolderProvisioner, IStaffRepository

logger = get_logger("staff.create_staff_member")


class CreateStaffMemberUseCase:
    def __init__(
        self,
        repository: IStaffRepository,
        email_sender: IEmailSender,
        invitation_expires_days: int,
        frontend_url: str,
        drive_folder_provisioner: Optional[IDriveFolderProvisioner] = None,
    ):
        self._repository = repository
        self._email_sender = email_sender
        self._invitation_expires_days = invitation_expires_days
        self._frontend_url = frontend_url
        # Opcional para no romper los tests existentes que no lo pasan —
        # mismo criterio que `UpdateStaffMemberUseCase.session_revoker`.
        self._drive_folder_provisioner = drive_folder_provisioner

    async def execute(
        self,
        *,
        full_name: str,
        email: str,
        job_title: Optional[str],
        department: Optional[str],
        entity_code: str,
        role_code: str,
        hire_date: Optional[date],
        vacation_days_override: Optional[float],
        invited_by: str,
    ) -> StaffMember:
        normalized_email = email.strip().lower()
        if await self._repository.find_by_email(normalized_email) is not None:
            raise StaffEmailAlreadyExistsError("Ya existe una persona con ese correo.")

        entity_id = await self._repository.resolve_entity_id(entity_code)
        if entity_id is None:
            raise InvalidEntityCodeError(f"La entidad '{entity_code}' no existe.")

        role_id = await self._repository.resolve_role_id(role_code)
        if role_id is None:
            raise InvalidRoleCodeError(f"El rol '{role_code}' no existe.")

        department_id = None
        if department:
            department_id = await self._repository.get_or_create_department_id(
                entity_id=entity_id, department_name=department
            )

        expires_at = datetime.now(timezone.utc) + timedelta(days=self._invitation_expires_days)
        member = await self._repository.create_staff_member(
            full_name=full_name,
            email=normalized_email,
            job_title=job_title,
            department_id=department_id,
            entity_id=entity_id,
            role_id=role_id,
            is_external=role_code == RoleCode.EXTERNO_INVITADO,
            hire_date=hire_date,
            vacation_days_override=vacation_days_override,
            invited_by=invited_by,
            expires_at=expires_at,
        )

        # Best-effort OBLIGATORIO (decisión de producto "hook en alta +
        # batch de backfill"): un fallo de Drive (timeout, credenciales,
        # error de API) NUNCA debe revertir ni bloquear el alta — la persona
        # ya existe en `users`/`invitations`, su carpeta se resuelve luego
        # (batch `POST /documents/provision-folders` o el primer upload
        # manual, `UploadDocumentUseCase.get_or_create_employee_folder`).
        if self._drive_folder_provisioner is not None:
            try:
                await self._drive_folder_provisioner.provision_folder(
                    member.id, member.email
                )
            except Exception as e:
                logger.error(
                    "Drive folder provisioning failed",
                    user_id=member.id,
                    email=member.email,
                    error=str(e),
                )

        # Best-effort: un fallo al enviar el aviso NO revierte el alta — la
        # persona ya existe en `users`/`invitations`, RRHH puede reenviarlo
        # a mano desde el feature `invitations` (mismo criterio que
        # `NotifyUseCase.execute`).
        try:
            await self._email_sender.send(
                to=member.email,
                template="staff_invited",
                context={"full_name": member.full_name, "frontend_url": self._frontend_url},
                user_id=member.id,
            )
        except Exception as e:
            logger.error(
                "Staff invitation email failed",
                user_id=member.id,
                email=member.email,
                error=str(e),
            )

        return member
