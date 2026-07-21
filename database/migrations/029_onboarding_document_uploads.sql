BEGIN;

-- Enlace explícito "este upload de employee_documents satisfizo el paso 3
-- de onboarding de ESTE usuario" (sdd/docs-firmados-upload-drive, D3): NO
-- alcanza con `employee_documents.category='signed'` como única fuente de
-- verdad, porque cualquier admin puede subir un documento `signed` para un
-- empleado vía `POST /documents` fuera del flujo de onboarding, y eso no
-- debe contar como "paso 3 completado". Mismo rol que cumplía
-- `document_signatures` (sin IP/hash — aquí no hay nada que trazar, es solo
-- el enlace) y mismo criterio de `ON DELETE RESTRICT` (un enlace de
-- onboarding no se borra en cascada por accidente).
CREATE TABLE IF NOT EXISTS onboarding_document_uploads (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    onboarding_document_id UUID NOT NULL REFERENCES onboarding_documents(id) ON DELETE RESTRICT,
    employee_document_id   UUID NOT NULL REFERENCES employee_documents(id) ON DELETE RESTRICT,
    uploaded_at            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_onboarding_document_upload_user_doc UNIQUE (user_id, onboarding_document_id)
);
CREATE INDEX IF NOT EXISTS idx_onboarding_document_uploads_user_id
    ON onboarding_document_uploads(user_id);

-- El paso 3 ya no se firma dentro de la plataforma — el título sembrado en
-- `020_onboarding_steps_seed.sql` induce a error ahora que la acción real es
-- subir el PDF ya firmado. Idempotente por el WHERE (no reescribe si un
-- admin ya lo personalizó desde `PATCH /onboarding/admin/steps/{id}`).
UPDATE onboarding_steps
SET title = 'Sube tu documentación firmada'
WHERE step_order = 3 AND title = 'Firma de documentación laboral';

COMMIT;
