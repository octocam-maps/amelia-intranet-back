BEGIN;

-- Multi-manual con LECTURA EN CASCADA en el paso 3 (RF-A6.1/RF-A6.3, que se
-- especificaron y nunca se implementaron del todo, + petición del 2026-07-31:
-- el manual de ClickUp se lee obligatoriamente ANTES de acceder al resto).
--
-- Hasta ahora el paso 3 era 1:1 paso<->documento: `find_active_document('manual')`
-- devolvía UNO (el de mayor `version`) y `ManualStep.tsx` pintaba un solo enlace
-- con un único botón de confirmación. El propio código lo avisaba: con un segundo
-- manual había que rehacerlo.
--
-- EL ORDEN VIVE EN EL DATO, no en el código — misma decisión que `step_order`
-- (ver 033_onboarding_steps_reorder_v11.sql): cambiar qué manual es la puerta es
-- un UPDATE, no un despliegue. Si el orden estuviera en una constante de Python,
-- RRHH no podría reordenar sus propios manuales.
ALTER TABLE onboarding_documents
    ADD COLUMN IF NOT EXISTS display_order INTEGER NOT NULL DEFAULT 1;

-- Los `signature` no usan cascada (hay uno solo), pero comparten tabla: el
-- DEFAULT 1 los deja neutros sin excepciones en la query.
COMMENT ON COLUMN onboarding_documents.display_order IS
    'Orden de lectura dentro de su `kind`. Para kind=manual define la CASCADA: '
    'no se puede confirmar un manual sin haber confirmado todos los de orden menor.';

-- El manual del Hincator (035) pasa a SEGUNDO: es material técnico del producto,
-- y quien entra nuevo necesita primero saber por dónde se comunica el equipo.
UPDATE onboarding_documents
SET display_order = 2,
    updated_at = CURRENT_TIMESTAMP
WHERE kind = 'manual'
  AND storage_ref = '/manuales/manual-usuario-hincator-2026-ES.pdf';

-- Manual de uso de ClickUp: PRIMERO, y por tanto la puerta del paso 3.
--
-- `content_hash` es el SHA-256 del fichero EXACTO que se sirve desde
-- `amelia-intranet-web/public/manuales/` — lo imprime
-- `amelia-intranet/docs/build-manual-pdf.py clickup --publish`. Si el PDF se
-- regenera, este hash deja de cuadrar y hay que actualizar la fila: es lo que
-- hace verificable la integridad de lo que el trabajador confirma haber leído
-- (RNF2.2).
--
-- Igual que el del Hincator y el de uso, se sirve como asset estático del
-- frontend y NO por `POST /documents`: es material corporativo que publicamos
-- nosotros, no una subida de un trabajador, así que
-- `DOCUMENTS_MAX_UPLOAD_MB` no le aplica (ver el razonamiento completo en
-- 035_onboarding_manual_hincator.sql).
--
-- Idempotente por el WHERE NOT EXISTS: reejecutar la migración no duplica la fila
-- ni pisa un título que un admin haya personalizado.
INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref, display_order)
SELECT 'manual',
       'Manual de uso de ClickUp',
       1,
       '03303afd373dfd67c5e1e22e696dcbd57d167a268f01570e8babdd2d3f14e98d',
       '/manuales/manual-clickup-2026-ES.pdf',
       1
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE kind = 'manual' AND storage_ref = '/manuales/manual-clickup-2026-ES.pdf'
);

-- El orden debe ser único DENTRO de cada kind, o "el siguiente de la cascada"
-- sería ambiguo y dos manuales empatados se desbloquearían de forma no
-- determinista. Índice parcial sobre los activos: un manual retirado
-- (`is_active = FALSE`) puede conservar su orden histórico sin bloquear al que
-- lo sustituye.
CREATE UNIQUE INDEX IF NOT EXISTS uq_onboarding_documents_active_order
    ON onboarding_documents (kind, display_order)
    WHERE is_active = TRUE;

-- El manual de uso de la INTRANET (`/manuales/manual-de-uso-intranet.pdf`, la
-- página de Ayuda) NO se añade aquí a propósito: no se pidió como lectura
-- obligatoria del onboarding, y meterlo alargaría el paso 3 sin que nadie lo
-- haya decidido. Cuando se quiera, es un INSERT con `display_order = 3` — el
-- fichero ya está publicado en la misma carpeta.

COMMIT;
