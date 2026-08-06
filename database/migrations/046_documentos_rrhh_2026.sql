BEGIN;

-- Documentación entregada por RRHH el 2026-08-06. Añade DOS manuales de lectura
-- obligatoria al paso 3 y sustituye el placeholder del paso 5 por los CUATRO
-- documentos reales que hay que firmar.
--
-- Hasta ahora el paso 5 tenía UNA fila con `storage_ref = NULL` y un
-- `content_hash` de relleno (`deadbeef...`), porque RRHH no había entregado el
-- PDF. Ya lo ha hecho, y no es uno: son cuatro documentos distintos.

-- ─────────────────────────────────────────────────────────────────────────────
-- 1 · Los dos manuales nuevos del paso 3
-- ─────────────────────────────────────────────────────────────────────────────
--
-- `requires_acknowledgement = TRUE`: los dos son de lectura obligatoria para
-- toda la plantilla (petición explícita de RRHH), así que entran en la CASCADA
-- del paso 3 y no solo en la biblioteca de consulta.
--
-- `display_order` 4 y 5: detrás de ClickUp (1), Hincator (2) y el manual de la
-- intranet (3). El orden IMPORTA aquí — en el paso 3 define qué se puede
-- confirmar y en qué momento (`ensure_manual_unlocked`).
--
-- `content_hash` = SHA-256 del PDF servido, tal como lo imprime
-- `amelia-intranet/docs/build-manual-pdf.py {acoso|politica} --publish`. Si el
-- PDF se regenera, hay que actualizar estas dos filas.

INSERT INTO onboarding_documents (
    kind, title, version, content_hash, storage_ref, display_order,
    requires_acknowledgement
)
SELECT 'manual',
       'Protocolo de prevención del acoso',
       1,
       'ab7f6b17dcdb1ebe77f69efeb9b5385b525991a77cb3917a8cfb861303654bdc',
       '/manuales/protocolo-acoso-amelia-2026.pdf',
       4,
       TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE kind = 'manual' AND storage_ref = '/manuales/protocolo-acoso-amelia-2026.pdf'
);

INSERT INTO onboarding_documents (
    kind, title, version, content_hash, storage_ref, display_order,
    requires_acknowledgement
)
SELECT 'manual',
       'Política Laboral 2026',
       1,
       'd6304ea3f0b4ea7e782bb5ef7d88502b0376c97cae6f7e2b0f62d77c46791927',
       '/manuales/politica-laboral-amelia-2026.pdf',
       5,
       TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE kind = 'manual' AND storage_ref = '/manuales/politica-laboral-amelia-2026.pdf'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2 · Retirada del placeholder del paso 5
-- ─────────────────────────────────────────────────────────────────────────────
--
-- VA ANTES DE LOS INSERT, y el orden no es estético: el índice parcial
-- `uq_onboarding_documents_cascade_order` vigila (kind, display_order) sobre las
-- filas activas con `requires_acknowledgement = TRUE`. El placeholder tiene
-- `display_order = 1` (el default) y chocaría con el primer documento nuevo.
-- Desactivarlo lo saca del índice y libera el puesto.
--
-- `is_active = FALSE` en vez de DELETE: si alguien ya subió su documentación
-- contra esta fila, `onboarding_document_uploads` la referencia y borrarla
-- destruiría el rastro de lo que esa persona entregó.
UPDATE onboarding_documents
   SET is_active = FALSE,
       updated_at = CURRENT_TIMESTAMP
 WHERE kind = 'signature'
   AND storage_ref IS NULL
   AND content_hash = 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef';

-- ─────────────────────────────────────────────────────────────────────────────
-- 3 · Los cuatro documentos a firmar del paso 5
-- ─────────────────────────────────────────────────────────────────────────────
--
-- `storage_ref = 'generated:<code>'` en vez de una ruta: estos PDF NO son un
-- fichero estático. Se generan por usuario, rellenados con los datos del perfil
-- del paso 4, en `onboarding/infrastructure/signable_documents.py` — el `<code>`
-- es la clave de su diccionario `BUILDERS`.
--
-- POR QUÉ NO VAN A `public/manuales/` COMO LOS MANUALES: los manuales son
-- idénticos para toda la plantilla, así que servirlos sin autenticación no
-- expone nada. Estos llevan dentro nombre, DNI y puesto de una persona
-- concreta. Se sirven solo por `GET /onboarding/documents/{id}/pdf`, que resuelve
-- el usuario desde el JWT (RGPD: el filtrado por usuario ocurre en el backend).
--
-- `content_hash` NO es el SHA-256 del fichero servido — no puede serlo, cada
-- persona recibe un PDF distinto. Es el hash de la REDACCIÓN
-- (`signable_documents.template_hash`), que es lo que hace falta para responder
-- a "qué texto aceptó esta persona" cuando el documento cambie de versión.
--
-- `display_order` aquí es SOLO presentación: el paso 5 no tiene cascada (ver
-- `resolve_step_documents(cascade=False)`). Los cuatro se pueden subir en
-- cualquier orden; lo que cierra el paso es que estén todos.

INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref, display_order)
SELECT 'signature',
       'Información sobre protección de datos personales',
       1,
       '50b86f3b9df81364577ab809c4eaed8f68cf88aa0bc6081d87d5f302f285b2c1',
       'generated:rgpd-informacion',
       1
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents WHERE storage_ref = 'generated:rgpd-informacion'
);

INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref, display_order)
SELECT 'signature',
       'Compromiso de confidencialidad y protección de datos',
       1,
       'dd49264d169124f85ae2814874f1d7c8682fde310865f4e61404c9b597a04667',
       'generated:compromiso-confidencialidad',
       2
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE storage_ref = 'generated:compromiso-confidencialidad'
);

INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref, display_order)
SELECT 'signature',
       'Consentimiento para la cesión de imágenes y datos personales',
       1,
       '51622c1cf54e82df0e9c00adc3e51ab90b6accae1fac7d6c16196849f3c5935a',
       'generated:consentimiento-imagenes',
       3
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE storage_ref = 'generated:consentimiento-imagenes'
);

-- El CES es el formulario del servicio de prevención ajeno Som Prevenció, no un
-- documento de Amelia: conserva SU maquetación y su naranja corporativo porque
-- es a ellos a quienes se remite firmado para su archivo. Ver la nota de
-- `_build_reconocimiento_medico`.
INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref, display_order)
SELECT 'signature',
       'Consentimiento para el examen de salud',
       1,
       '7f8a1b164703ef6357e941a7b3eb7b9d09f73d7e425925fa90ffc53f0b71b7d0',
       'generated:reconocimiento-medico',
       4
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE storage_ref = 'generated:reconocimiento-medico'
);

COMMIT;
