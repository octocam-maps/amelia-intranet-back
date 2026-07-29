"""Fixtures de `OnboardingStep`/`OnboardingDocument` compartidas entre los
tests de casos de uso — mismo shape que sembrará
`020_onboarding_steps_seed.sql`, para que los tests no se desincronicen del
seed real."""

from src.features.onboarding.domain.entities import OnboardingDocument, OnboardingStep

VIDEO_STEP = OnboardingStep(
    id="step-video",
    step_order=1,
    type="video",
    title="Bienvenida a Amelia",
    config={"url": "/src/assets/videos/hincator.mp4", "duration": 96},
    is_active=True,
)

QUIZ_STEP = OnboardingStep(
    id="step-quiz",
    step_order=2,
    type="quiz",
    title="Cuestionario: El Hincator",
    config={
        "threshold": 0.7,
        "questions": [
            {
                "id": "q1",
                "text": "¿Cuántos parámetros?",
                "options": ["5", "7"],
                "correct": "7",
            },
            {
                "id": "q2",
                "text": "¿Cuánto tiempo?",
                "options": ["15s", "5s"],
                "correct": "15s",
            },
            {
                "id": "q3",
                "text": "¿Cuántas por hora?",
                "options": ["50", "100"],
                "correct": "100",
            },
            {
                "id": "q4",
                "text": "¿Qué garantiza la conexión?",
                "options": ["4G", "Starlink"],
                "correct": "Starlink",
            },
        ],
    },
    is_active=True,
)

MANUAL_STEP = OnboardingStep(
    id="step-manual",
    step_order=3,
    type="manual",
    # Título actualizado por `033_onboarding_steps_reorder_v11.sql` — el paso
    # pasa a ser la lectura de TODOS los manuales de referencia, no solo el
    # del empleado (el seed 020 decía "Manual del empleado", histórico).
    title="Manuales",
    config={},
    is_active=True,
)

PROFILE_STEP = OnboardingStep(
    id="step-profile",
    step_order=4,
    type="profile",
    title="Completa tu perfil",
    config={},
    is_active=True,
)

SIGNATURE_STEP = OnboardingStep(
    id="step-signature",
    step_order=5,
    type="signature",
    # Título actualizado por `029_onboarding_document_uploads.sql`
    # (sdd/docs-firmados-upload-drive) — el sembrado original en
    # `020_onboarding_steps_seed.sql` decía "Firma de documentación laboral"
    # (histórico, esa migración no se toca). El `type` sigue siendo
    # `signature` (D6: no se renombra el discriminador).
    title="Sube tu documentación firmada",
    config={},
    is_active=True,
)

# Orden vigente tras `033_onboarding_steps_reorder_v11.sql` (v1.1 RRHH): la
# documentación firmada es EL ÚLTIMO paso y los manuales suben al 3, para que
# nadie llegue a las plantillas sin haber leído antes la documentación de
# referencia. La lista está en el orden real de `step_order`.
ALL_STEPS = [VIDEO_STEP, QUIZ_STEP, MANUAL_STEP, PROFILE_STEP, SIGNATURE_STEP]

SIGNATURE_DOCUMENT = OnboardingDocument(
    id="doc-signature",
    kind="signature",
    title="Documentación laboral",
    version=1,
    content_hash="deadbeef" * 8,
    storage_ref=None,
    is_active=True,
)

# Material REAL desde `035_onboarding_manual_hincator.sql` — antes era el
# placeholder ("Manual del empleado", `cafebabe…`, sin `storage_ref`). El
# fichero se sirve como asset estático del front (`public/manuales/`), igual
# que el vídeo del paso 1: el límite de 10 MB de `POST /documents` protege las
# subidas de los TRABAJADORES, no el material corporativo que publicamos.
MANUAL_DOCUMENT = OnboardingDocument(
    id="doc-manual",
    kind="manual",
    title="Manual de usuario Hincator® 2026",
    version=1,
    content_hash="b72ce8011190e141b650e3b87a2bd6e15c9e903958035852a545f80473d90731",
    storage_ref="/manuales/manual-usuario-hincator-2026-ES.pdf",
    is_active=True,
)
