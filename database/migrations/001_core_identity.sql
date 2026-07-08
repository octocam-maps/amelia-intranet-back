BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Entidades legales del grupo: Hub / Lab / Ops
CREATE TABLE IF NOT EXISTS entities (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code       VARCHAR(20) NOT NULL UNIQUE CHECK (code IN ('hub', 'lab', 'ops')),
    name       VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Departamentos (jerárquicos) → base del organigrama (Fase 5)
CREATE TABLE IF NOT EXISTS departments (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id            UUID NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    parent_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    name                 VARCHAR(120) NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_departments_entity_id ON departments(entity_id);

-- Roles del sistema (administrador / empleado / externo_invitado)
CREATE TABLE IF NOT EXISTS roles (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code       VARCHAR(30) NOT NULL UNIQUE
                 CHECK (code IN ('administrador', 'empleado', 'externo_invitado')),
    name       VARCHAR(80) NOT NULL,
    is_system  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Usuarios. Identidad delegada en Google OIDC → sin password.
CREATE TABLE IF NOT EXISTS users (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email          VARCHAR(255) NOT NULL UNIQUE,          -- se normaliza a minúsculas en app
    google_sub     VARCHAR(255) UNIQUE,                   -- NULL hasta el primer login con Google
    hosted_domain  VARCHAR(255),                          -- claim hd (ameliahub.com para internos)
    full_name      VARCHAR(160) NOT NULL,
    avatar_url     TEXT,
    role_id        UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    entity_id      UUID REFERENCES entities(id) ON DELETE SET NULL,       -- NULL para externo
    department_id  UUID REFERENCES departments(id) ON DELETE SET NULL,
    manager_id     UUID REFERENCES users(id) ON DELETE SET NULL,         -- línea de reporte (organigrama)
    job_title      VARCHAR(120),
    status         VARCHAR(20) NOT NULL DEFAULT 'invited'
                     CHECK (status IN ('invited', 'active', 'suspended')),
    is_external    BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_users_role_id    ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_entity_id  ON users(entity_id);
CREATE INDEX IF NOT EXISTS idx_users_manager_id ON users(manager_id);
CREATE INDEX IF NOT EXISTS idx_users_status     ON users(status);

-- Perfil RRHH (datos sensibles RGPD → cifrado en reposo recomendado).
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id                 UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    dni_nif                 VARCHAR(20),
    birth_date              DATE,
    phone                   VARCHAR(30),
    address                 TEXT,
    emergency_contact_name  VARCHAR(160),
    emergency_contact_phone VARCHAR(30),
    iban                    VARCHAR(34),                  -- para volcado de nóminas
    social_security_number  VARCHAR(30),
    completed_at            TIMESTAMPTZ,                  -- paso 5 del onboarding
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Invitaciones (alta de plantilla y de externos con Gmail personal).
CREATE TABLE IF NOT EXISTS invitations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       VARCHAR(255) NOT NULL,
    role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    entity_id   UUID REFERENCES entities(id) ON DELETE SET NULL,
    token       VARCHAR(120) NOT NULL UNIQUE,
    invited_by  UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'accepted', 'revoked', 'expired')),
    expires_at  TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invitations_email  ON invitations(email);
CREATE INDEX IF NOT EXISTS idx_invitations_status ON invitations(status);

INSERT INTO roles (code, name) VALUES
    ('administrador',    'Administrador'),
    ('empleado',         'Empleado'),
    ('externo_invitado', 'Externo-invitado')
ON CONFLICT (code) DO NOTHING;

INSERT INTO entities (code, name) VALUES
    ('hub', 'Amelia Hub'),
    ('lab', 'Amelia Lab'),
    ('ops', 'Amelia Ops')
ON CONFLICT (code) DO NOTHING;

COMMIT;
