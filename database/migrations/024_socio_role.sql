BEGIN;

-- Rol "socio" (docs/permisos-roles.md aún no lo documenta — decisión de
-- producto posterior al modelo de 3 roles): igual que un EMPLEADO en TODA
-- la app + visión global del calendario de vacaciones (ver + exportar
-- PDF/Excel) + recibe emails de cumpleaños/anuncios (audiencia
-- team/all ya lo incluye, solo excluye `externo_invitado` — ver
-- `notifications/infrastructure/repositories/notification_repository.py`).
-- NO es admin: no aprueba ausencias, no gestiona festivos/tipos de ausencia,
-- no ve el buzón anónimo ni el resto de "Administración".
ALTER TABLE roles DROP CONSTRAINT roles_code_check;
ALTER TABLE roles ADD CONSTRAINT roles_code_check
    CHECK (code IN ('administrador', 'empleado', 'externo_invitado', 'socio'));

INSERT INTO roles (code, name) VALUES
    ('socio', 'Socio')
ON CONFLICT (code) DO NOTHING;

COMMIT;
