BEGIN;

-- Rol "tecnico" (requerimiento v1.2 §M1, decisión del team-lead del
-- 2026-08-06): los técnicos de campo no fichan por tramos como el resto de la
-- plantilla — cumplimentan un PARTE DIARIO (proyecto, lugar, horario, pausa,
-- pernocta, categoría de producto) y se rigen por una bolsa de 162 h
-- mensuales, no por la jornada estándar.
--
-- POR QUÉ UN ROL Y NO UN RÉGIMEN HORARIO EN `users`: se propuso
-- `users.time_tracking_regime` (ortogonal al rol, de modo que un técnico
-- pudiera ser además socio o administrador sin perder su cómputo) y el
-- team-lead eligió el rol, con la objeción sobre la mesa. Queda anotado el
-- coste aceptado: un técnico que cambie de rol pierde su régimen de cómputo, y
-- cada rol futuro obliga a revisar las tuplas de `src/shared/auth/roles.py`.
--
-- CÓMO SE MANTIENE ACOTADO EL CAMBIO (mismo criterio que la migración 038): el
-- rol se AÑADE a `ALL_ROLES` y a `INTERNAL_ROLES`, así que hereda por defecto
-- todo lo que ve un empleado y las features futuras también. Lo que cambia es
-- solo su forma de registrar jornada:
--   * NO entra en `TIME_CLOCK_ROLES` — el fichaje por tramos, el reloj en vivo
--     y el alta en lote no son suyos.
--   * SÍ entra en `DAILY_TIME_LOG_ROLES` — el grupo nuevo de "quién debe
--     registrar su jornada cada día", que es lo que alimenta el recordatorio
--     diario (RF-A4.3). Sin ese grupo, derivar la exclusión de
--     `TIME_CLOCK_ROLES` habría dejado al técnico SIN recordatorio, justo a
--     quien el parte le es obligatorio a diario.
ALTER TABLE roles DROP CONSTRAINT roles_code_check;
ALTER TABLE roles ADD CONSTRAINT roles_code_check
    CHECK (code IN (
        'administrador', 'empleado', 'externo_invitado', 'socio', 'becario', 'tecnico'
    ));

INSERT INTO roles (code, name) VALUES
    ('tecnico', 'Técnico')
ON CONFLICT (code) DO NOTHING;

-- Ningún usuario se migra a este rol aquí, a propósito: quién es técnico lo
-- decide RRHH desde la ficha de Plantilla, y así el cambio queda registrado en
-- `user_role_history` (migración 039) con autor y fecha, en vez de aparecer
-- como un UPDATE anónimo de una migración. Mismo criterio que 038 con los
-- becarios.

COMMIT;
