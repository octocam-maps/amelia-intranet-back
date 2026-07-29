BEGIN;

-- El cuestionario del onboarding pasa de UN intento a un MÁXIMO DE DOS
-- (decisión de producto del team-lead, 2026-07-29).
--
-- Esto rectifica una regla que estaba escrita como "no negociable" en
-- `CLAUDE.md` ("el cuestionario del paso 2 es de un único intento") y en el
-- requerimiento original. El cambio es deliberado: con un solo intento, quien
-- falla queda atascado en el paso 2 y necesita que un admin le reinicie el
-- intento a mano (`POST /onboarding/admin/.../reset-quiz`) para poder seguir.
--
-- `uq_quiz_attempt_single UNIQUE(user_id, step_id)` era LA garantía real de
-- "un intento" bajo concurrencia (doble clic, dos pestañas), no un adorno. Al
-- retirarla hay que sustituirla por otra garantía equivalente o se abre la
-- puerta a intentos ilimitados por carrera: `attempt_number` +
-- `UNIQUE(user_id, step_id, attempt_number)`. Con eso, dos peticiones
-- simultáneas que ambas calculen "me toca el intento 2" colisionan y solo una
-- gana — exactamente el mismo blindaje que antes, pero por número de intento.
ALTER TABLE onboarding_quiz_attempts
    ADD COLUMN IF NOT EXISTS attempt_number INTEGER NOT NULL DEFAULT 1;

-- Los intentos que ya existan son necesariamente el primero: la UNIQUE que
-- estamos a punto de quitar impedía tener más de uno por usuario/paso. El
-- DEFAULT 1 de arriba ya los deja correctos, no hace falta backfill.
ALTER TABLE onboarding_quiz_attempts
    DROP CONSTRAINT IF EXISTS uq_quiz_attempt_single;

-- El `DROP ... IF EXISTS` de la restricción NUEVA no es redundante: sin él, un
-- segundo pase de esta migración aborta con `relation
-- "uq_quiz_attempt_per_number" already exists`. Este proyecto no tiene runner de
-- migraciones ni tabla de control (`database/migrations/` se aplica a mano con
-- psql), así que reejecutar una migración no es un accidente improbable: es lo
-- que va a pasar. El `CHECK` de más abajo ya venía protegido; esta no, y era una
-- asimetría sin motivo.
ALTER TABLE onboarding_quiz_attempts
    DROP CONSTRAINT IF EXISTS uq_quiz_attempt_per_number;
ALTER TABLE onboarding_quiz_attempts
    ADD CONSTRAINT uq_quiz_attempt_per_number UNIQUE (user_id, step_id, attempt_number);

-- Solo se valida que el número sea positivo, NO que sea <= 2: el techo de
-- intentos es una regla de producto y vive en un único sitio
-- (`domain/policy.py::MAX_QUIZ_ATTEMPTS`). Ponerlo también aquí obligaría a
-- una migración para cambiar un número y permitiría que ambos valores se
-- desincronizaran. Lo que la BD garantiza es lo que solo la BD puede
-- garantizar: que no haya dos intentos con el mismo número (la carrera).
ALTER TABLE onboarding_quiz_attempts
    DROP CONSTRAINT IF EXISTS ck_quiz_attempt_number_positive;
ALTER TABLE onboarding_quiz_attempts
    ADD CONSTRAINT ck_quiz_attempt_number_positive CHECK (attempt_number >= 1);

COMMIT;
