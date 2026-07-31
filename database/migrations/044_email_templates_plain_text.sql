BEGIN;

-- Las plantillas de correo pasan a guardar TEXTO PLANO, no HTML.
--
-- POR QUÉ: la 041 dejaba que el admin escribiera `<p>Hola {{full_name}},</p>`, y
-- eso es pedirle a una persona de RRHH que escriba código. Consecuencias reales
-- de dejarlo así:
--   · una etiqueta mal cerrada rompe el correo de TODA la plantilla, y no se
--     descubre hasta que llega a las bandejas;
--   · escribir un `<` en un texto normal ("<3", "temperatura < 5º") lo convierte
--     en una etiqueta a medias;
--   · el editor pedía una habilidad que el puesto no tiene, así que el resultado
--     previsible era que nadie lo tocara o que lo tocara mal.
--
-- AHORA: el admin escribe el texto tal cual, con líneas en blanco para separar
-- párrafos. El HTML lo genera `plain_text_to_html` en el backend, que además
-- ESCAPA todo lo que escriba: ya no puede romper el correo ni inyectar markup,
-- aunque quiera.
--
-- Se admite `**negrita**` (igual que WhatsApp) y las URLs y correos se enlazan
-- solos. No es una etiqueta: es una convención que ya conoce cualquiera.

-- La columna se RENOMBRA porque `body_html` mentiría: ya no guarda HTML. Un
-- nombre que miente es peor que un nombre largo — el siguiente que lo lea
-- asumirá que puede meter etiquetas.
-- ───────────────────────────────────────────────────────────────────────────
--  LOCK TIMEOUT — leer esto antes de ejecutar en producción
--
--  `ALTER TABLE ... RENAME COLUMN` necesita un ACCESS EXCLUSIVE LOCK. El
--  renombrado en sí es instantáneo (solo toca metadatos), pero CONSEGUIR el lock
--  no lo es: el backend lee `email_templates` en cada envío de correo
--  (`PostgresEmailTemplateProvider`), así que cualquier conexión con una
--  transacción abierta sobre esa tabla lo hace esperar.
--
--  Y esperar es lo PELIGROSO: un ACCESS EXCLUSIVE pendiente encola a todo el que
--  llegue detrás, incluidas las lecturas. Sin este timeout, una migración que
--  "tarda" 5 minutos no tarda: cuelga la aplicación 5 minutos.
--
--  Con `lock_timeout` falla en 5 segundos y revierte todo. Es LOCAL a esta
--  transacción: no cambia la configuración del servidor.
--
--  SI FALLA POR TIMEOUT, mira quién tiene la tabla ocupada:
--
--    SELECT pid, state, wait_event_type, now() - xact_start AS duracion,
--           left(query, 80) AS query
--    FROM pg_stat_activity
--    WHERE datname = current_database() AND pid <> pg_backend_pid()
--      AND (state = 'idle in transaction' OR query ILIKE '%email_templates%')
--    ORDER BY xact_start;
--
--  Lo habitual es una conexión `idle in transaction` del pool del backend. Lo más
--  limpio es PARAR el backend, aplicar y arrancarlo con el código nuevo — que
--  además hace falta: esta migración NO es retrocompatible, el código anterior
--  lee `body_html` y esa columna deja de existir.
-- ───────────────────────────────────────────────────────────────────────────
SET LOCAL lock_timeout = '5s';

ALTER TABLE email_templates RENAME COLUMN body_html TO body;

COMMENT ON COLUMN email_templates.body IS
    'Cuerpo en TEXTO PLANO escrito por el administrador. Línea en blanco = '
    'párrafo nuevo; `**texto**` = negrita; las URLs y correos se enlazan solos. '
    'El HTML lo genera `plain_text_to_html` y escapa este contenido: aquí NO se '
    'guardan etiquetas.';

-- Convierte lo que sembró la 041. Son dos formas conocidas y cerradas, así que
-- se transforman con `replace` en vez de con una regex genérica que podría
-- estropear un texto que el admin ya hubiera personalizado.
--
-- `<p>x</p><p>y</p>` -> "x\n\ny"  ·  `<p>x</p>` -> "x"
UPDATE email_templates
SET body = btrim(
        replace(
            replace(
                replace(body, '</p><p>', E'\n\n'),
                '<p>', ''),
            '</p>', '')
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE body LIKE '%<p>%';

-- Guardia: si queda alguna etiqueta suelta, la conversión no cubrió un caso y es
-- mejor enterarse aquí que ver `&lt;strong&gt;` literal en un correo (el
-- renderizador escapa el texto, así que una etiqueta superviviente se vería tal
-- cual en la bandeja de entrada del destinatario).
DO $guardia$
DECLARE
    con_etiquetas INTEGER;
BEGIN
    SELECT count(*) INTO con_etiquetas
    FROM email_templates
    WHERE body ~ '<[a-zA-Z/][^>]*>' OR subject ~ '<[a-zA-Z/][^>]*>';

    IF con_etiquetas > 0 THEN
        RAISE EXCEPTION
            'Quedan % plantillas con etiquetas HTML sin convertir. Revísalas a '
            'mano antes de continuar: el cuerpo ahora se escapa, así que una '
            'etiqueta superviviente se vería literal en el correo.', con_etiquetas;
    END IF;
END
$guardia$;

COMMIT;
