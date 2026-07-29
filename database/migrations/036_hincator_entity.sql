BEGIN;

-- `Hincator` como CUARTA sociedad del grupo (decisión del team-lead,
-- 2026-07-29). No es una línea de producto dentro de otra sociedad: tiene 19 de
-- los 36 trabajadores de la plantilla —más que Hub, Lab y Ops juntas, que suman
-- 17—, su propio COO en el C-Level, y personal en cuatro departamentos.
-- Ver `amelia-intranet/docs/seed-plantilla-bloqueantes.md`.
--
-- El `CHECK` de `entities.code` (001_core_identity.sql) lo impedía. Se recrea
-- con el cuarto valor en vez de eliminarse: la lista cerrada es intencionada,
-- evita que un typo en un PATCH cree una sociedad fantasma.

ALTER TABLE entities
    DROP CONSTRAINT IF EXISTS entities_code_check;

ALTER TABLE entities
    ADD CONSTRAINT entities_code_check
        CHECK (code IN ('hub', 'lab', 'ops', 'hincator'));

INSERT INTO entities (code, name) VALUES
    ('hincator', 'Hincator')
ON CONFLICT (code) DO NOTHING;

-- Los 5 departamentos, para las CUATRO entidades.
--
-- Y sí, también para las tres que ya existían: los 15 departamentos del entorno
-- de desarrollo se insertaron A MANO el 2026-07-15 y NINGUNA migración los
-- reproduce, así que un entorno nuevo se levanta con entidades y **cero
-- departamentos**. Se arregla aquí porque es el mismo agujero: no se puede
-- sembrar Hincator sin darse cuenta de que los otros tampoco estaban.
--
-- El producto cartesiano es deliberado. `departments` no tiene CRUD propio (ver
-- 016): el admin los nombra libremente al dar de alta gente, así que tener el
-- juego completo por entidad es lo que permite asignar sin crear duplicados a
-- mano. `uq_departments_entity_name` hace el `ON CONFLICT` seguro.
INSERT INTO departments (entity_id, name)
SELECT e.id, d.name
FROM entities e
CROSS JOIN (VALUES
    ('Administración'),
    ('Comercial'),
    ('Ingeniería'),
    ('Operaciones'),
    ('Producto')
) AS d(name)
ON CONFLICT (entity_id, name) DO NOTHING;

-- Guarda: si el CHECK no admitiera 'hincator', el INSERT de arriba habría
-- fallado ya; esto cubre el caso de que la entidad exista pero sin
-- departamentos (p. ej. si alguien la creó a mano antes de esta migración).
DO $$
DECLARE
    faltan INTEGER;
BEGIN
    SELECT COUNT(*) INTO faltan
    FROM entities e
    WHERE (SELECT COUNT(*) FROM departments d WHERE d.entity_id = e.id) < 5;

    IF faltan > 0 THEN
        RAISE EXCEPTION
            'Quedan % entidades con menos de 5 departamentos — la siembra no se completó.', faltan;
    END IF;
END $$;

COMMIT;
