BEGIN;

-- Alcance del aviso de incorporación al equipo (petición del 2026-07-31:
-- "cada vez que alguien se añada/invite al portal de Amelia se mande un mail de
-- bienvenida y aviso a todo el equipo", con el destinatario configurable por el
-- admin).
--
-- POR QUÉ VIVE EN `email_templates` Y NO EN UNA TABLA DE AJUSTES: hoy hay
-- exactamente UN aviso con alcance configurable, y una tabla de settings para una
-- fila es más estructura que problema. Además el admin edita el texto y el
-- destinatario en la misma pantalla, que es como piensa la decisión: "cuando
-- alguien entra, manda ESTE texto a ESTA gente".
--
-- La columna es NULLABLE y solo significa algo para las plantillas de fan-out. En
-- las demás (`absence_approved`, `payslip_available`…) el destinatario no se
-- elige: es la persona a la que le pasó la cosa.
ALTER TABLE email_templates
    ADD COLUMN IF NOT EXISTS audience VARCHAR(20),
    ADD COLUMN IF NOT EXISTS audience_entity_id UUID REFERENCES entities(id) ON DELETE SET NULL;

-- `none` es imprescindible: el admin tiene que poder APAGAR el aviso al equipo
-- sin dejar de mandar la bienvenida al recién llegado. `is_active = FALSE` no
-- sirve para eso — significa "usa el texto por defecto", no "no envíes".
--
-- NO hay `role`: avisar de una incorporación "solo a los socios" no tiene uso
-- práctico y añadiría una dimensión que nadie ha pedido. Se puede sumar después
-- ampliando este CHECK.
ALTER TABLE email_templates
    DROP CONSTRAINT IF EXISTS ck_email_templates_audience;
ALTER TABLE email_templates
    ADD CONSTRAINT ck_email_templates_audience CHECK (
        audience IS NULL OR audience IN ('all', 'entity', 'none')
    );

-- `entity` sin entidad elegida sería un fan-out a nadie, en silencio.
ALTER TABLE email_templates
    DROP CONSTRAINT IF EXISTS ck_email_templates_audience_entity;
ALTER TABLE email_templates
    ADD CONSTRAINT ck_email_templates_audience_entity CHECK (
        audience <> 'entity' OR audience_entity_id IS NOT NULL
    );

-- Por defecto, toda la plantilla: es lo que se pidió ("aviso a todo el equipo").
-- `list_announcement_recipient_ids` ya excluye SIEMPRE a `externo_invitado`, así
-- que "todos" nunca incluye a los colaboradores externos.
UPDATE email_templates
SET audience = 'all',
    updated_at = CURRENT_TIMESTAMP
WHERE template_key = 'staff_joined_team'
  AND audience IS NULL;

COMMIT;
