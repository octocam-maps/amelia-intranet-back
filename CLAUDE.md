# CLAUDE.md — amelia-intranet-back

Guía para Claude Code (claude.ai/code) en este repositorio.

## Qué es

API de la **intranet de RRHH y onboarding del grupo Amelia** (Hub / Lab / Ops). Sustituye a Holded y
centraliza gestión laboral hoy externalizada. **FastAPI + asyncpg con SQL crudo**, arquitectura
hexagonal por feature.

Sirve a DOS clientes con el mismo contrato: `amelia-intranet-web` (React + Vite) y
`amelia-intranet-mobile` (React Native + Expo). Un cambio en un endpoint afecta a los dos — comprueba
siempre si el móvil consume lo que estás tocando.

La documentación funcional vive en el repo hermano `amelia-intranet/` (`docs/permisos-roles.md` es la
fuente de verdad de control de acceso; `docs/requerimientos-v1.1-rrhh.md` la ampliación vigente).

Es un proyecto **nuevo e independiente** del stack de inspección solar del grupo (`amelia-back`,
`backend2`). Comparte convenciones con `backend2` — hexagonal, asyncpg, feature-sliced — pero no
código ni base de datos.

## Comandos

```bash
pytest                      # 145 ficheros de test. pytest.ini: testpaths=src, asyncio_mode=auto
ruff check src              # línea de 88, comillas dobles, isort con src como first-party
ruff format src
python run_server.py        # servidor local
```

**No hay Makefile ni scripts de npm.** No inventes `make test`.

## Arquitectura: hexagonal por feature

Cada feature en `src/features/<nombre>/` con las tres capas, y NUNCA se salta el orden:

```
domain/          modelos, políticas y PUERTOS (Protocol). Cero dependencias de FastAPI o asyncpg
application/     use_cases/ — un fichero por caso de uso. Recibe puertos, no implementaciones
infrastructure/  routes.py (FastAPI) + repositories/ (asyncpg, SQL crudo). Implementa los puertos
```

Los tests viven junto a la capa que prueban (`domain/tests/`, `application/tests/`,
`infrastructure/tests/`), no en un árbol paralelo.

18 features: `absences`, `announcements`, `auth`, `dashboard`, `departments`, `documents`,
`email_templates`, `holidays`, `invitations`, `mailbox`, `notifications`, `onboarding`, `profile`,
`roles`, `staff`, `team`, `time_clock`.

`src/shared/` es transversal: `config.py`, `database`, `auth`, `jwt`, `google_oidc`, `email`,
`errors`, `logger`, `middleware`, `utils`, `assets`.

**SQL crudo con asyncpg, no ORM.** No introduzcas SQLAlchemy ni Alembic: la migración de esquema es
manual y deliberada (ver abajo).

## Migraciones

`database/migrations/`, numeradas `001` a `045`, **se aplican a mano** en orden. `database/init.sql`
levanta una base desde cero.

Dos trampas reales de esta carpeta:

- **El número `044` está usado dos veces.** `044_email_templates_plain_text.sql` es la migración;
  `044_comprobar_estado.sql` NO lo es — es un script de diagnóstico de solo lectura que se versionó
  aquí. Es inofensivo si se ejecuta, pero no cuenta como migración. Si añades una nueva, el siguiente
  número libre es el `046`.
- Al desplegar, una migración sin aplicar no rompe el arranque: rompe el primer endpoint que toca la
  tabla. Aplícala ANTES de subir el código que la necesita.

## Autenticación

**Google OIDC exclusivamente** — no hay login con contraseña. El flujo es: el cliente obtiene un
`id_token` de Google, lo manda a `POST /auth/login`, y el backend devuelve un JWT de acceso más una
cookie `HttpOnly` de refresco.

Lo que no es negociable:

- **Rotación de refresh con detección de reutilización** (OWASP). Si llega un refresh ya consumido, se
  revoca la FAMILIA entera (`revoke_family()`), no solo ese token. Es la defensa contra el robo de
  cookie: el atacante y la víctima se anulan mutuamente.
- **Un solo `audience`.** `src/shared/google_oidc/verifier.py` valida contra un único client-id, y eso
  es lo que condiciona qué apps pueden entrar. Antes de "arreglar" el login del móvil, entiende esta
  restricción.
- `POST /auth/login` está limitado a **10 peticiones por minuto** (`slowapi`). Cualquier automatización
  que haga login repetido debe cachear la sesión o se comerá 429.

### `GOOGLE_OIDC_PROVIDER=fake` — solo en tu máquina

Existe un verificador falso (`src/shared/google_oidc/fake_verifier.py`) para que las pruebas E2E del
web puedan autenticar sin Google. **Es un bypass total de autenticación.** El valor por defecto es
`google` y en producción no hay que tocar nada.

Tiene dos guardas independientes, y las dos deben seguir ahí:

1. Si `ENVIRONMENT` es `prod` o `stage` y el proveedor no es `google` → el arranque falla.
2. Si `REFRESH_TOKEN_COOKIE_SECURE` está activo y el proveedor no es `google` → el arranque falla.
   Esta segunda existe porque la primera no cubre el olvido de exportar `ENVIRONMENT`.

Cada verificación falsa emite un `logger.critical`. En los logs de producción **nunca** debe aparecer
`FAKE Google OIDC verifier en uso`.

## Modelo de roles

Cinco valores en `src/shared/auth/roles.py`. La matriz completa está en
`amelia-intranet/docs/permisos-roles.md`.

| Rol | Alcance |
|---|---|
| `administrador` | Único (People Manager). Bandejas de aprobación, calendarios globales, sección Administración |
| `empleado` | Toda la plantilla. Solo lo suyo; lectura del equipo |
| `socio` | Como empleado + calendario global de vacaciones (ver y exportar). NO administra |
| `becario` | Como empleado, sin control horario (RF-A10) |
| `externo_invitado` | Onboarding parcial (vídeo + manuales), directorio y organigrama en lectura |

**Ocultar en la UI no es proteger.** Todo endpoint debe rechazar al rol no autorizado con
`require_role(...)`. Escribir la URL a mano no puede dar acceso — el filtrado por usuario ocurre aquí,
nunca en el cliente.

## Reglas de dominio que no se negocian

- **El fichaje nunca admite fecha futura**, ni en alta unitaria ni en lote. Es el fix del hallazgo de
  pentest LOGIC-2 (ALTA) y la naturaleza del registro de jornada del art. 34.9 ET. El alta manual hacia
  el pasado está acotada por `TIME_CLOCK_MANUAL_ENTRY_MAX_PAST_DAYS`.
- **Onboarding secuencial con bloqueo**, orden vigente (migración `033`): 1 vídeo · 2 cuestionario ·
  3 manuales · 4 perfil · 5 documentación firmada. Subir la documentación es lo que finaliza el
  onboarding — el perfil ya NO es el último paso.
- **Cuestionario: máximo 2 intentos** (`MAX_QUIZ_ATTEMPTS`, migración `034`). Es el único sitio donde
  vive el techo. Al fallar se muestran las preguntas erradas **por su id**, nunca la respuesta
  correcta: revelarla convertiría el segundo intento en un trámite.
- **RGPD:** cada trabajador accede solo a sus propios registros (nóminas, contrato, documentos,
  perfil).
- **Firma digital trazable:** fecha, hora, IP y hash del documento.

## Integraciones

- **Google Drive API** — volcado de nóminas, contratos y documentos.
- **SendGrid** — ~12 tipos de notificación. Remitente verificado: `info@amelia.am`.
- **Cron externo de ops** → `POST /notifications/jobs/run?job=daily` (cumpleaños, aniversarios y el
  recordatorio diario de fichaje RF-A4). **No hay scheduler dentro del servicio**: sin ese cron, esas
  notificaciones no se envían nunca.

## Idioma

Español de España en todo lo que ve el usuario: mensajes de error de la API, copys de correo y
plantillas. El código, los identificadores y los nombres de tabla en inglés.
