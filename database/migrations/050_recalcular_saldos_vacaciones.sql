BEGIN;

-- Recalcula `entitled_days` de los saldos de VACACIONES ya creados, para que
-- cuadren con la política nueva (23 días base + tramos por antigüedad de la
-- «Política Laboral Amelia Hub 2026» §5-§6).
--
-- POR QUÉ HACE FALTA UNA MIGRACIÓN Y NO LO ARREGLA EL CÓDIGO SOLO:
-- `get_or_create_balance` (`absences/infrastructure/repositories/
-- absence_repository.py`) hace SELECT y, si la fila EXISTE, la devuelve tal cual
-- —solo calcula al INSERTAR—. Es deliberado: el saldo es un dato de negocio que
-- no debe moverse solo bajo los pies de nadie. Consecuencia: desplegar la
-- política nueva NO actualiza a quien ya tiene saldo de este año, y se queda con
-- la cifra vieja mientras el manual que acaba de leer promete otra.
--
-- Medido antes de escribir esto: 28 de 40 filas de 2026 quedaban desactualizadas.
--
-- QUÉ NO TOCA, y es lo que hace esta migración segura:
--   · `used_days` y `pending_days` — lo ya disfrutado y lo pendiente de aprobar
--     no se altera. Esto solo mueve el TECHO, así que nadie pierde días ni se
--     queda con un saldo negativo por el camino.
--   · Los años CERRADOS (`year < año en curso`) — el entitlement de un ejercicio
--     pasado es un hecho consumado y recalcularlo reescribiría un histórico.
--   · Las filas de cualquier tipo de ausencia que no sea `vacaciones`: los demás
--     tipos tienen su propio `default_entitled_days` y no dependen de la
--     antigüedad.
--   · Las filas con `vacation_days_override` fijado, que conservan su valor: un
--     override es una decisión manual del administrador y manda sobre el cálculo
--     automático (mismo orden que `resolve_vacation_entitlement_days`).
--
-- La fórmula ESPEJA `absences/domain/vacation_entitlement.py`. Se verificó la
-- equivalencia entre este SQL y esa función comparando las 228 fechas de alta
-- posibles (2010-2028 × 12 meses) más el caso `hire_date IS NULL`. Si la política
-- vuelve a cambiar, hay que tocar los DOS sitios y volver a comprobarlo.

WITH esperado AS (
    SELECT b.id AS balance_id,
           b.entitled_days AS actual,
           CASE
               -- El override manual del admin manda, exactamente como en
               -- `resolve_vacation_entitlement_days`.
               WHEN u.vacation_days_override IS NOT NULL
                   THEN u.vacation_days_override
               WHEN u.hire_date IS NULL THEN 0
               WHEN EXTRACT(YEAR FROM u.hire_date)::int > b.year THEN 0
               WHEN EXTRACT(YEAR FROM u.hire_date)::int < b.year THEN
                   CASE
                       -- Antigüedad efectiva, ya con la "regla de los seis
                       -- meses" de §6 aplicada: si el aniversario cae con seis
                       -- meses o menos de año natural por delante, el tramo que
                       -- abre no cuenta hasta el año siguiente.
                       WHEN GREATEST(
                                b.year - EXTRACT(YEAR FROM u.hire_date)::int
                                  - CASE
                                        WHEN (12 - EXTRACT(MONTH FROM u.hire_date)::int) > 6
                                            THEN 0
                                        ELSE 1
                                    END,
                                0
                            ) >= 5 THEN 25
                       WHEN GREATEST(
                                b.year - EXTRACT(YEAR FROM u.hire_date)::int
                                  - CASE
                                        WHEN (12 - EXTRACT(MONTH FROM u.hire_date)::int) > 6
                                            THEN 0
                                        ELSE 1
                                    END,
                                0
                            ) >= 3 THEN 24
                       ELSE 23
                   END
               -- Año de incorporación: se prorratea la BASE por meses trabajados
               -- (el mes de alta cuenta) y se redondea al MEDIO DÍA hacia arriba.
               ELSE CEIL(
                        23.0 * (12 - EXTRACT(MONTH FROM u.hire_date)::int + 1) / 12.0 * 2
                    ) / 2
           END AS nuevo
    FROM absence_balances b
    JOIN absence_types t ON t.id = b.absence_type_id AND t.code = 'vacaciones'
    JOIN users u ON u.id = b.user_id
    WHERE b.year >= EXTRACT(YEAR FROM CURRENT_DATE)::int
      AND u.deleted_at IS NULL
)
UPDATE absence_balances b
   SET entitled_days = e.nuevo,
       updated_at = CURRENT_TIMESTAMP
  FROM esperado e
 WHERE b.id = e.balance_id
   -- Solo las que de verdad cambian: así `updated_at` no miente sobre las filas
   -- que ya estaban bien.
   AND b.entitled_days <> e.nuevo;

COMMIT;

-- Comprobación: no debe quedar ninguna fila del año en curso cuyo
-- `entitled_days` difiera de lo que dicta la política.
SELECT count(*) AS filas_desactualizadas
FROM absence_balances b
JOIN absence_types t ON t.id = b.absence_type_id AND t.code = 'vacaciones'
JOIN users u ON u.id = b.user_id
WHERE b.year >= EXTRACT(YEAR FROM CURRENT_DATE)::int
  AND u.deleted_at IS NULL
  AND b.entitled_days <> CASE
      WHEN u.vacation_days_override IS NOT NULL THEN u.vacation_days_override
      WHEN u.hire_date IS NULL THEN 0
      WHEN EXTRACT(YEAR FROM u.hire_date)::int > b.year THEN 0
      WHEN EXTRACT(YEAR FROM u.hire_date)::int < b.year THEN
          CASE
              WHEN GREATEST(b.year - EXTRACT(YEAR FROM u.hire_date)::int
                    - CASE WHEN (12 - EXTRACT(MONTH FROM u.hire_date)::int) > 6
                           THEN 0 ELSE 1 END, 0) >= 5 THEN 25
              WHEN GREATEST(b.year - EXTRACT(YEAR FROM u.hire_date)::int
                    - CASE WHEN (12 - EXTRACT(MONTH FROM u.hire_date)::int) > 6
                           THEN 0 ELSE 1 END, 0) >= 3 THEN 24
              ELSE 23
          END
      ELSE CEIL(23.0 * (12 - EXTRACT(MONTH FROM u.hire_date)::int + 1) / 12.0 * 2) / 2
  END;

-- Reparto resultante, para leerlo de un vistazo tras aplicar.
SELECT b.entitled_days AS dias, count(*) AS personas
FROM absence_balances b
JOIN absence_types t ON t.id = b.absence_type_id AND t.code = 'vacaciones'
JOIN users u ON u.id = b.user_id
WHERE b.year = EXTRACT(YEAR FROM CURRENT_DATE)::int AND u.deleted_at IS NULL
GROUP BY b.entitled_days ORDER BY b.entitled_days DESC;
