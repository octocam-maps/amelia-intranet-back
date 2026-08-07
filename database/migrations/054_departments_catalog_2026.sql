BEGIN;

-- Catálogo de departamentos 2026 (petición de Beatriz Luna, 2026-08-06):
-- Marketing · Operaciones · Producto (con Software y Hardware colgando) ·
-- I+D · Ventas.
--
-- El catálogo anterior (5 nombres × 4 entidades, sembrado en la migración 036)
-- era: Administración · Comercial · Ingeniería · Operaciones · Producto. NO es
-- un subconjunto del nuevo, así que esto NO es un cambio de catálogo: es una
-- MIGRACIÓN DE DATOS. Hay personas asignadas y `users.department_id` las
-- referencia.
--
-- POR QUÉ `is_active` Y NO UN DELETE: `users.department_id` es
-- `ON DELETE SET NULL`. Borrar `Administración` dejaría a su gente sin
-- departamento EN SILENCIO — sin error, sin traza, y sin forma de saber a
-- posteriori dónde estaban. Desactivar los saca del desplegable sin tocar una
-- sola asignación: RRHH los reasigna persona a persona desde la ficha de
-- Plantilla, y hasta que lo haga cada uno conserva su valor actual.
--
-- SOFTWARE Y HARDWARE CUELGAN DE PRODUCTO (`parent_department_id`, que ya
-- existía en 001 sin usarse). Ojo: NO son lo mismo que la categoría de
-- producto del parte del técnico (`technician_daily_logs.product_category`).
-- Son dos ejes distintos y comparten nombre por casualidad: alguien del
-- departamento de Hardware puede pasar una jornada imputada a Software.

ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_departments_is_active
    ON departments(is_active) WHERE is_active;

-- 1 · Renombrado con equivalencia directa. Va PRIMERO y no como INSERT+UPDATE
--     porque conserva `departments.id` y, con él, todas las asignaciones de
--     `users.department_id`. Insertar "Ventas" antes chocaría además con
--     `uq_departments_entity_name` al renombrar después.
--
--     Guarda: si en alguna entidad ya existiera "Ventas" junto a "Comercial",
--     el renombrado violaría la UNIQUE. En ese caso se deja "Comercial" para
--     revisión manual en vez de tumbar la migración entera.
UPDATE departments d
SET name = 'Ventas', updated_at = CURRENT_TIMESTAMP
WHERE d.name = 'Comercial'
  AND NOT EXISTS (
      SELECT 1 FROM departments x
      WHERE x.entity_id = d.entity_id AND x.name = 'Ventas'
  );

-- 2 · Los departamentos raíz del catálogo nuevo, para las CUATRO entidades.
--     Producto y Operaciones ya existían: el ON CONFLICT los respeta con su
--     id intacto (y por tanto con su gente).
INSERT INTO departments (entity_id, name)
SELECT e.id, d.name
FROM entities e
CROSS JOIN (VALUES
    ('Marketing'),
    ('Operaciones'),
    ('Producto'),
    ('I+D'),
    ('Ventas')
) AS d(name)
ON CONFLICT (entity_id, name) DO NOTHING;

-- 3 · Software y Hardware, colgando del Producto de SU MISMA entidad.
INSERT INTO departments (entity_id, name, parent_department_id)
SELECT parent.entity_id, child.name, parent.id
FROM departments parent
CROSS JOIN (VALUES ('Software'), ('Hardware')) AS child(name)
WHERE parent.name = 'Producto'
ON CONFLICT (entity_id, name) DO NOTHING;

-- 3b · Si Software/Hardware ya existían sueltos de una siembra anterior, se
--      les cuelga de Producto en vez de duplicarlos.
UPDATE departments child
SET parent_department_id = parent.id, updated_at = CURRENT_TIMESTAMP
FROM departments parent
WHERE child.name IN ('Software', 'Hardware')
  AND parent.name = 'Producto'
  AND parent.entity_id = child.entity_id
  AND child.parent_department_id IS DISTINCT FROM parent.id;

-- 4 · Fuera del catálogo nuevo, SIN equivalencia posible:
--     - `Administración`: desaparece; RRHH decide a dónde va su gente.
--     - `Ingeniería`: se divide en Software / Hardware / I+D, y esa decisión
--       es persona a persona — ninguna regla automática puede repartirla.
--     Se desactivan; nadie pierde su asignación.
UPDATE departments
SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
WHERE name IN ('Administración', 'Ingeniería');

-- 5 · Guarda final (mismo criterio que la migración 036): si alguna entidad no
--     queda con los 7 departamentos activos esperados (5 raíz + Software +
--     Hardware), la migración entera se revierte en vez de dejar el catálogo
--     a medias.
DO $$
DECLARE
    incompletas INTEGER;
BEGIN
    SELECT COUNT(*) INTO incompletas
    FROM entities e
    WHERE (
        SELECT COUNT(*) FROM departments d
        WHERE d.entity_id = e.id AND d.is_active
          AND d.name IN ('Marketing','Operaciones','Producto','I+D','Ventas','Software','Hardware')
    ) < 7;

    IF incompletas > 0 THEN
        RAISE EXCEPTION
            'Quedan % entidades sin los 7 departamentos activos del catálogo 2026.', incompletas;
    END IF;
END $$;

-- Reversión (no automática — requiere decidir qué hacer con las asignaciones
-- hechas mientras tanto):
--   UPDATE departments SET is_active = TRUE WHERE name IN ('Administración', 'Ingeniería');
--   UPDATE departments SET name = 'Comercial' WHERE name = 'Ventas';
--   UPDATE departments SET is_active = FALSE WHERE name IN ('Marketing', 'I+D', 'Software', 'Hardware');

COMMIT;
