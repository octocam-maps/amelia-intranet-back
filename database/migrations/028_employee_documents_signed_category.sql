BEGIN;

-- Categoría "Firmados" (sdd/docs-firmados-upload-drive): el paso 3 del
-- onboarding deja de firmar dentro de la plataforma y pasa a exigir la
-- subida del PDF ya firmado fuera de ella — ese documento se indexa como
-- `employee_documents.category='signed'` para que aparezca en "Documentos"
-- del propio empleado, igual que nóminas/contratos. Nombre de constraint
-- confirmado en `004_documents.sql` (CHECK sin nombre explícito -> nombre
-- por defecto de Postgres `<tabla>_<columna>_check`).
ALTER TABLE employee_documents
    DROP CONSTRAINT IF EXISTS employee_documents_category_check;
ALTER TABLE employee_documents
    ADD CONSTRAINT employee_documents_category_check
    CHECK (category IN ('payslip', 'contract', 'general', 'other', 'signed'));

COMMIT;
