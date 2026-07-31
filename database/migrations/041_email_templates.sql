BEGIN;

-- Plantillas de email editables por el administrador (petición del 2026-07-31:
-- "que estos mensajes automáticos de mails pueda editarlos en algún apartado").
--
-- QUÉ HABÍA ANTES: `render_email` (`shared/email/infrastructure/
-- sendgrid_email_sender.py`) tiene DOS ramas, no 13 plantillas: `staff_invited`
-- con su asunto y cuerpo propios, y un fallback genérico que envuelve el
-- `title`/`body` que cada caso de uso escribe en Python. Así que el admin no
-- podía tocar ni un asunto sin un despliegue.
--
-- QUÉ SE EDITA Y QUÉ NO: solo `subject` y `body_html`. El MARCO del correo
-- (`_shell`: cabecera con logo, botón de CTA, pie) sigue en código y no se
-- expone. Si el admin pudiera editar el HTML completo, un correo mal guardado
-- saldría sin logo o con el layout roto para toda la plantilla, y nadie se
-- daría cuenta hasta que llegara a las bandejas.
--
-- PLACEHOLDERS: `{{nombre}}` con lista blanca por plantilla, resueltos en
-- `render_email`. Los VALORES se escapan siempre (`html.escape`): el asunto y el
-- cuerpo los escribe el admin, pero `full_name` o `job_title` vienen de datos y
-- no deben poder inyectar markup. Un placeholder desconocido se deja literal y
-- se registra — nunca revienta el envío.
CREATE TABLE IF NOT EXISTS email_templates (
    -- Clave natural: coincide 1:1 con el `template` que pasa `IEmailSender.send`
    -- (y ese, con el `type` de la notificación in-app). Un `id` UUID aparte
    -- obligaría a un JOIN para responder "¿qué plantilla usa este envío?".
    template_key VARCHAR(80) PRIMARY KEY,
    -- Etiqueta y descripción para la pantalla de administración: sin esto, el
    -- admin vería una lista de slugs (`clock_out_missing`) y tendría que
    -- adivinar cuándo se manda cada correo.
    label        VARCHAR(120) NOT NULL,
    description  TEXT NOT NULL,
    subject      TEXT NOT NULL,
    body_html    TEXT NOT NULL,
    -- `FALSE` = "usa el texto por defecto del código". Es el botón "Restaurar"
    -- de la pantalla: desactivar en vez de borrar la fila conserva lo que el
    -- admin había escrito, por si quiere volver.
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed con los textos que HOY están en el código, para que activar la edición no
-- cambie ni una coma de lo que reciben los trabajadores. El admin parte de lo
-- que ya se enviaba.
--
-- Las plantillas que hoy usan el fallback genérico se siembran con
-- `{{title}}`/`{{body}}`: su contenido lo sigue escribiendo el caso de uso (una
-- ausencia aprobada tiene que decir QUÉ ausencia), y lo que el admin puede
-- cambiar es el envoltorio y el tono alrededor.
INSERT INTO email_templates (template_key, label, description, subject, body_html) VALUES
    ('staff_invited',
     'Bienvenida al dar de alta',
     'Se envía a la persona recién dada de alta en la intranet, con el enlace para entrar con su cuenta de Google.',
     'Te damos la bienvenida a la intranet de Amelia',
     '<p>Hola {{full_name}},</p><p>RRHH te ha dado de alta en la intranet de Amelia. Accede con tu cuenta de Google corporativa para completar tu onboarding y empezar a gestionar tu jornada, ausencias y documentos.</p>'),

    ('staff_joined_team',
     'Aviso al equipo de una incorporación',
     'Se envía al equipo cuando se da de alta a alguien nuevo. El alcance de destinatarios se configura aparte.',
     'Nueva incorporación en Amelia: {{full_name}}',
     '<p>{{full_name}} se incorpora a {{entity_name}} como {{job_title}}.</p><p>Dadle la bienvenida cuando os cruceis.</p>'),

    ('absence_requested',    'Ausencia solicitada',   'Al administrador, cuando alguien solicita una ausencia.',               '{{title}}', '<p>{{body}}</p>'),
    ('absence_approved',     'Ausencia aprobada',     'A la persona solicitante, cuando el administrador aprueba su ausencia.', '{{title}}', '<p>{{body}}</p>'),
    ('absence_rejected',     'Ausencia rechazada',    'A la persona solicitante, cuando el administrador rechaza su ausencia.', '{{title}}', '<p>{{body}}</p>'),
    ('announcement_published', 'Anuncio publicado',   'A la audiencia del anuncio cuando se publica o se edita.',              '{{title}}', '<p>{{body}}</p>'),
    ('payslip_available',    'Nómina disponible',     'A la persona, cuando se publica una nómina en su carpeta.',             '{{title}}', '<p>{{body}}</p>'),
    ('document_uploaded',    'Documento nuevo',       'A la persona, cuando se sube un documento a su carpeta.',                '{{title}}', '<p>{{body}}</p>'),
    ('mailbox_message',      'Mensaje del buzón anónimo', 'Al administrador, cuando entra un mensaje anónimo. NUNCA incluye datos del remitente.', '{{title}}', '<p>{{body}}</p>'),
    ('clock_in_reminder',    'Recordatorio de fichaje', 'Diario de lunes a viernes, a quien no ha fichado. No se envía a externos ni becarios.',   '{{title}}', '<p>{{body}}</p>'),
    ('clock_out_missing',    'Jornada sin cerrar',    'A quien dejó un fichaje abierto el día anterior.',                      '{{title}}', '<p>{{body}}</p>'),
    ('birthday',             'Cumpleaños',            'Al equipo, el día del cumpleaños de un compañero.',                     '{{title}}', '<p>{{body}}</p>'),
    ('work_anniversary',     'Aniversario laboral',   'Al equipo, en el aniversario de incorporación de un compañero.',        '{{title}}', '<p>{{body}}</p>'),
    ('onboarding_completed', 'Onboarding completado', 'Al administrador, cuando alguien termina su onboarding.',               '{{title}}', '<p>{{body}}</p>'),
    ('document_pending_signature', 'Documentación pendiente de firmar', 'A la persona, recordando que le queda subir la documentación firmada.', '{{title}}', '<p>{{body}}</p>')
ON CONFLICT (template_key) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_email_templates_active
    ON email_templates(template_key) WHERE is_active = TRUE;

COMMIT;
