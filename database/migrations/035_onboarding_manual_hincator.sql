BEGIN;

-- Sustituye el placeholder del manual de onboarding por el material REAL:
-- Manual de usuario Hincator® 2026 (ES). RF-A6.2.
--
-- El `020_onboarding_steps_seed.sql` dejó `content_hash = 'cafebabe'*8` y
-- `storage_ref = NULL` esperando el fichero definitivo; hasta ahora el paso de
-- manuales pedía confirmar la lectura de un documento que no se podía abrir.
--
-- POR QUÉ SE SIRVE COMO ASSET ESTÁTICO (y no subiéndolo por la API): el
-- manual pesa 12,65 MB y `DOCUMENTS_MAX_UPLOAD_MB` son 10, lo que se documentó
-- como bloqueante (RF-A6.4) dando por supuesto que el manual tenía que pasar
-- por `POST /documents`. No tiene por qué: ese límite protege las subidas de
-- los TRABAJADORES (documentación firmada, nóminas), no el material
-- corporativo que publicamos nosotros. El manual es material corporativo, del
-- mismo tipo que el vídeo del paso 1 (`/src/assets/videos/hincator.mp4`) o el
-- organigrama (`public/organigrama/`), así que se sirve igual: fichero
-- estático versionado en el repo del front. Eso deja RF-A6.4 sin efecto y
-- evita recomprimir el PDF (que además habría invalidado el hash de
-- referencia).
--
-- `content_hash` es el SHA-256 del fichero EXACTO que se sirve al trabajador,
-- sin comprimir — coincide con el del original archivado en
-- `amelia-intranet/docs/manuales/manual-usuario-hincator-2026-ES.pdf`. Es lo
-- que hace verificable la integridad de lo que el trabajador confirma haber
-- leído (RNF2.2): si el fichero cambia, el hash deja de cuadrar.
--
-- Idempotente por el WHERE sobre el placeholder: si un admin ya personalizó el
-- título o si esta migración ya corrió, no se reescribe nada.
UPDATE onboarding_documents
SET title = 'Manual de usuario Hincator® 2026',
    storage_ref = '/manuales/manual-usuario-hincator-2026-ES.pdf',
    content_hash = 'b72ce8011190e141b650e3b87a2bd6e15c9e903958035852a545f80473d90731',
    updated_at = CURRENT_TIMESTAMP
WHERE kind = 'manual'
  AND content_hash = 'cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe';

-- La versión en INGLÉS queda fuera de alcance (RF-A6.5, decisión del
-- team-lead: manual solo en español). Cuando entre, será un documento NUEVO
-- (`kind='manual'`, otra fila) y entonces sí hará falta el soporte
-- multi-manual de RF-A6.1/RF-A6.3: hoy hay exactamente un manual real, así
-- que `find_active_document('manual')` sigue siendo suficiente.

COMMIT;
