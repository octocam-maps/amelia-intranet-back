BEGIN;

-- Parte diario del técnico (requerimiento v1.2 §M1). Campos pedidos por RRHH:
-- proyecto, lugar de trabajo, hora de inicio, hora de fin, si hubo pausa y de
-- cuánto, si hubo pernocta y si fue en España o fuera, y la categoría de
-- producto (Software/Hardware).
--
-- POR QUÉ SATÉLITE DE `time_clock_entries` Y NO UNA TABLA INDEPENDIENTE: el
-- art. 34.9 ET obliga a registrar la jornada de TODA la plantilla, y el
-- informe XLSX de RRHH (`time_clock/infrastructure/xlsx_export.py`) se
-- construye sobre `time_clock_entries`. Si el técnico viviera fuera de esa
-- tabla, desaparecería del registro legal sin que nadie lo notara. Aquí el
-- tramo (fecha, entrada, salida) sigue siendo un fichaje normal; esta tabla
-- solo añade el detalle de campo, y así el dashboard, el fichaje en vivo y el
-- móvil no tienen que convivir con diez columnas que para ellos son NULL.

-- Catálogo de proyectos. Sin él, "Proyecto" sería texto libre: a los tres
-- meses habría ocho formas de escribir "Guadix" y el resumen mensual que pide
-- RRHH no podría agrupar por nada. Mismo patrón que `absence_types`.
CREATE TABLE IF NOT EXISTS projects (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code       VARCHAR(40) NOT NULL UNIQUE,
    name       VARCHAR(160) NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_projects_is_active ON projects(is_active) WHERE is_active;

-- Redundante con la PK, pero es lo que permite la FK COMPUESTA de abajo. Sin
-- ella, `user_id` y `work_date` estarían copiados en el satélite y NADA
-- impediría que se desincronizaran del tramo padre — y de esas dos columnas
-- depende la regla "un parte por técnico y día".
ALTER TABLE time_clock_entries
    ADD CONSTRAINT uq_time_clock_entries_id_user_date UNIQUE (id, user_id, work_date);

CREATE TABLE IF NOT EXISTS technician_daily_logs (
    entry_id         UUID PRIMARY KEY REFERENCES time_clock_entries(id) ON DELETE CASCADE,

    -- Copiadas del tramo padre, no por comodidad de consulta: son las dos
    -- columnas sobre las que se impone `uq_technician_daily_logs_one_per_day`,
    -- y la FK compuesta las mantiene atadas a su origen.
    user_id          UUID NOT NULL,
    work_date        DATE NOT NULL,

    project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    work_location    VARCHAR(160) NOT NULL,

    -- `had_break` es redundante con `break_minutes > 0`, pero es un dato
    -- DECLARADO por la persona, no derivado: "no hubo pausa" y "hubo pausa de
    -- 0 minutos" son afirmaciones distintas ante una inspección de trabajo.
    had_break        BOOLEAN NOT NULL,
    break_minutes    INTEGER NOT NULL DEFAULT 0 CHECK (break_minutes >= 0),

    -- Un único campo en vez de booleano + lugar: así el estado imposible
    -- "no hubo pernocta pero fue en España" no se puede ni escribir. La UI sí
    -- pregunta en dos pasos, como pidió RRHH.
    overnight_stay   VARCHAR(12) NOT NULL DEFAULT 'ninguna'
                       CHECK (overnight_stay IN ('ninguna', 'espana', 'extranjero')),

    -- Software/Hardware SE CONSERVAN (decisión del team-lead del 2026-08-06).
    -- Es un eje distinto del departamento: alguien del departamento Hardware
    -- puede pasar una jornada imputada a Software, así que NUNCA se deriva de
    -- `users.department_id` — se pregunta en cada parte.
    product_category VARCHAR(20) NOT NULL
                       CHECK (product_category IN ('software', 'hardware')),

    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_technician_daily_logs_entry
        FOREIGN KEY (entry_id, user_id, work_date)
        REFERENCES time_clock_entries (id, user_id, work_date) ON DELETE CASCADE,

    -- "Se creará un registro diario que cada técnico deberá cumplimentar":
    -- uno, no varios tramos como en el fichaje estándar.
    CONSTRAINT uq_technician_daily_logs_one_per_day UNIQUE (user_id, work_date),

    CONSTRAINT chk_break_consistency
        CHECK ((had_break AND break_minutes > 0) OR (NOT had_break AND break_minutes = 0))
);

CREATE INDEX IF NOT EXISTS idx_technician_daily_logs_user_date
    ON technician_daily_logs(user_id, work_date);
CREATE INDEX IF NOT EXISTS idx_technician_daily_logs_project
    ON technician_daily_logs(project_id);
-- Parcial: el resumen mensual solo cuenta las pernoctas que existen, y
-- 'ninguna' es la mayoría de las filas.
CREATE INDEX IF NOT EXISTS idx_technician_daily_logs_overnight
    ON technician_daily_logs(overnight_stay) WHERE overnight_stay <> 'ninguna';

COMMIT;
