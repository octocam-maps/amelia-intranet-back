BEGIN;

-- Control horario: sesión de fichaje (entrada/salida) + pausas asociadas.
CREATE TABLE IF NOT EXISTS time_clock_entries (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    work_date  DATE NOT NULL,
    clock_in   TIMESTAMPTZ NOT NULL,
    clock_out  TIMESTAMPTZ,                  -- NULL = jornada abierta
    source     VARCHAR(20) NOT NULL DEFAULT 'web' CHECK (source IN ('web', 'mobile')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_time_clock_entries_user_date ON time_clock_entries(user_id, work_date);

CREATE TABLE IF NOT EXISTS time_clock_breaks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entry_id    UUID NOT NULL REFERENCES time_clock_entries(id) ON DELETE CASCADE,
    break_start TIMESTAMPTZ NOT NULL,
    break_end   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_time_clock_breaks_entry_id ON time_clock_breaks(entry_id);

-- Tipos de ausencia (configurable, Fase 5).
CREATE TABLE IF NOT EXISTS absence_types (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            VARCHAR(40) NOT NULL UNIQUE,
    name            VARCHAR(120) NOT NULL,
    is_paid         BOOLEAN NOT NULL DEFAULT TRUE,
    affects_balance BOOLEAN NOT NULL DEFAULT TRUE,   -- descuenta del cómputo de días
    color           VARCHAR(9),                       -- hex para el calendario
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Saldo por usuario / tipo / año → alimenta el "contador en tiempo real".
CREATE TABLE IF NOT EXISTS absence_balances (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    absence_type_id UUID NOT NULL REFERENCES absence_types(id) ON DELETE CASCADE,
    year            INTEGER NOT NULL,
    entitled_days   NUMERIC(5,1) NOT NULL DEFAULT 0,
    used_days       NUMERIC(5,1) NOT NULL DEFAULT 0,   -- solicitudes aprobadas
    pending_days    NUMERIC(5,1) NOT NULL DEFAULT 0,   -- solicitudes en revisión
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_balance_user_type_year UNIQUE (user_id, absence_type_id, year)
);

-- Solicitudes de ausencia con aprobación del admin.
CREATE TABLE IF NOT EXISTS absence_requests (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    absence_type_id UUID NOT NULL REFERENCES absence_types(id) ON DELETE RESTRICT,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    days_count      NUMERIC(5,1) NOT NULL,     -- laborables, excluye finde/festivos
    reason          TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    reviewed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (end_date >= start_date)
);
CREATE INDEX IF NOT EXISTS idx_absence_requests_user_id ON absence_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_absence_requests_status  ON absence_requests(status);
CREATE INDEX IF NOT EXISTS idx_absence_requests_dates   ON absence_requests(start_date, end_date);

-- Festivos (configurable, Fase 5). Para cómputo de días y calendario.
CREATE TABLE IF NOT EXISTS holidays (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    day        DATE NOT NULL,
    name       VARCHAR(120) NOT NULL,
    entity_id  UUID REFERENCES entities(id) ON DELETE CASCADE,   -- NULL = aplica a todas
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_holiday_day_entity UNIQUE (day, entity_id)
);

COMMIT;
