BEGIN;

-- Firma nativa eliminada (sdd/docs-firmados-upload-drive): el paso 3 ya no
-- firma dentro de la plataforma, sube el PDF ya firmado (`028`/`029` +
-- `employee_documents.category='signed'` + `onboarding_document_uploads`).
-- Verificado que ninguna otra tabla tiene una FK `REFERENCES
-- document_signatures` (grep completo del backend, sin coincidencias) — el
-- DROP es seguro a nivel de integridad referencial. IRREVERSIBLE: sin
-- histórico que preservar (decisión de producto), sin migración de vuelta.
-- Se aplica al FINAL de PR2 (no en el cleanup de código, `PR1`) — solo una
-- vez que el reemplazo completo (backend + frontend) está verificado
-- funcionando, no apenas se limpia el código que la usaba.
DROP TABLE IF EXISTS document_signatures;

COMMIT;
