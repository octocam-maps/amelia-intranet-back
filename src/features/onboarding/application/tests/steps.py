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

SIGNATURE_STEP = OnboardingStep(
    id="step-signature",
    step_order=3,
    type="signature",
    title="Firma de documentación laboral",
    config={},
    is_active=True,
)

MANUAL_STEP = OnboardingStep(
    id="step-manual",
    step_order=4,
    type="manual",
    title="Manual del empleado",
    config={},
    is_active=True,
)

PROFILE_STEP = OnboardingStep(
    id="step-profile",
    step_order=5,
    type="profile",
    title="Completa tu perfil",
    config={},
    is_active=True,
)

ALL_STEPS = [VIDEO_STEP, QUIZ_STEP, SIGNATURE_STEP, MANUAL_STEP, PROFILE_STEP]

SIGNATURE_DOCUMENT = OnboardingDocument(
    id="doc-signature",
    kind="signature",
    title="Documentación laboral",
    version=1,
    content_hash="deadbeef" * 8,
    storage_ref=None,
    is_active=True,
)

MANUAL_DOCUMENT = OnboardingDocument(
    id="doc-manual",
    kind="manual",
    title="Manual del empleado",
    version=1,
    content_hash="cafebabe" * 8,
    storage_ref=None,
    is_active=True,
)
