BEGIN;

-- RF §4.1.2 (Gestión de plantilla): el entitlement anual de vacaciones pasa
-- a calcularse AUTOMÁTICAMENTE a partir de `users.hire_date` (ver la fórmula
-- pura en `src/features/absences/domain/vacation_entitlement.py`) en lugar
-- de que el admin lo escriba siempre a mano.
--
-- DECISIÓN DE NEGOCIO (posterior al requerimiento, deroga el "23 días/año"
-- fijo de §4.1.2): devengo de 10 días laborables por cada semestre completo
-- (6 meses) trabajado — ver el docstring del módulo de dominio citado arriba
-- para el detalle de la fórmula y sus casos límite.
--
-- El admin conserva la capacidad de FIJAR el valor a mano (override) para
-- casos particulares (acuerdos individuales, convenios, etc.). Se necesita
-- una columna nullable dedicada — separada de `absence_balances.entitled_days`
-- (que es NOT NULL y ya tiene que llevar SIEMPRE un valor concreto para que
-- la aritmética de saldo funcione) — para poder distinguir "sin override,
-- calcular automáticamente" (NULL) de "con override, ese valor manda"
-- (no NULL). Mismo patrón que `holidays.entity_id` + `clear_entity` para
-- distinguir "no tocar" de "vaciar" en una actualización parcial.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS vacation_days_override NUMERIC(5,1);

COMMENT ON COLUMN users.vacation_days_override IS
    'Override manual del admin sobre el entitlement anual de vacaciones. '
    'NULL = automático (calculado desde hire_date). No-NULL = el valor '
    'fijado manda sobre el cálculo automático.';

COMMIT;
