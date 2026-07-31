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
