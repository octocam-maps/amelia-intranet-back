BEGIN;

-- Rol "becario" (RF-A10, decisión del team-lead del 2026-07-31): un becario
-- accede a TODO lo que ve un empleado SALVO el módulo de control horario.
--
-- POR QUÉ UN ROL Y NO UN TIPO DE CONTRATO: ya existe
-- `users.contract_type = 'intern'` (migración 037), pero ese campo es
-- informativo y no lo consulta ningún guard — habría que meterlo en el JWT o
-- resolverlo por SELECT en cada request para que decidiera permisos. Se elige
-- el rol porque el permiso ES lo que se quiere expresar, y porque
-- `require_role` ya sabe leerlo del claim `role` sin tocar la autenticación.
--
-- CÓMO SE MANTIENE ACOTADO EL CAMBIO (ver `src/shared/auth/roles.py`): el rol
-- se AÑADE a `ALL_ROLES` y a `INTERNAL_ROLES`, así que los 41 endpoints que
-- hoy usan esos grupos le dan acceso sin tocarse, y cualquier endpoint futuro
-- también — que es exactamente "acceso a todo". Lo que se restringe es solo
-- el fichaje, vía el grupo nuevo `TIME_CLOCK_ROLES`. Si se hubiera hecho al
-- revés (rol excluido por defecto, añadido endpoint a endpoint), cada feature
-- nueva sería una decisión más y un olvido dejaría al becario fuera en
-- silencio.
--
-- ATENCIÓN, RELACIÓN LABORAL: el art. 34.9 ET obliga a registrar la jornada de
-- las PERSONAS TRABAJADORAS. Un contrato formativo en alternancia (art. 11 ET)
-- SÍ es relación laboral y su jornada debe registrarse; una práctica académica
-- externa (RD 592/2014, vía convenio con el centro) no lo es. Este rol NO
-- distingue los dos casos — igual que no lo hace `contract_type='intern'`.
-- Pendiente de validación por RRHH antes de producción: si hay que
-- distinguirlos, el sitio es `contract_type`, no un rol nuevo.
ALTER TABLE roles DROP CONSTRAINT roles_code_check;
ALTER TABLE roles ADD CONSTRAINT roles_code_check
    CHECK (code IN ('administrador', 'empleado', 'externo_invitado', 'socio', 'becario'));

INSERT INTO roles (code, name) VALUES
    ('becario', 'Becario')
ON CONFLICT (code) DO NOTHING;

-- Los dos becarios reales de la plantilla (documentados en
-- `amelia-intranet/docs/seed-plantilla-bloqueantes.md`) NO se migran aquí a
-- propósito: hoy son `empleado` + `contract_type='intern'` y cambiarles el rol
-- les quita el fichaje, que es precisamente lo que está pendiente de
-- validación laboral. Lo hará RRHH desde la ficha de Plantilla cuando lo
-- confirme, y así el cambio queda registrado en `user_role_history`
-- (migración 039) con autor y fecha, en vez de aparecer como un UPDATE
-- anónimo de una migración.

COMMIT;
