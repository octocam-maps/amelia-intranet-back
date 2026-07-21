"""
Test route-level: `quiz` y `complete-profile` son exclusivos de roles
internos — el externo-invitado debe rechazarse en el BACKEND (403), no solo
ocultarse del navbar. `video-progress` y `acknowledge` sí están abiertos al
externo-invitado (onboarding parcial). Mismo patrón que
`features/absences/infrastructure/tests/test_absences_routes.py`.
"""

import io
import os
from datetime import datetime, timezone
from typing import Optional

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent"
)

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

from src.features.onboarding.domain.entities import OnboardingDocumentUpload  # noqa: E402
from src.features.onboarding.infrastructure import (
    dependencies as onboarding_dependencies,  # noqa: E402
)
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {
            "sub": "user-1",
            "email": "user@ameliahub.com",
            "role": role,
            "entity_id": None,
            "is_external": role == "externo_invitado",
        }
    )


def test_externo_invitado_cannot_submit_quiz():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-quiz/quiz",
                json={"answers": {"q1": "7"}},
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_complete_profile():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-profile/complete-profile",
                json={},
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_complete_profile_rejects_an_empty_body_with_422():
    """RF §3.5: el DTO exige los 6 campos obligatorios — un body vacío se
    rechaza en la capa de Pydantic, sin llegar al caso de uso."""
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-profile/complete-profile",
                json={},
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_complete_profile_rejects_a_whitespace_only_full_name_with_422():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-profile/complete-profile",
                json={
                    "full_name": "   ",
                    "birth_date": "1990-05-20",
                    "dni_nie": "12345678Z",
                    "personal_phone": "+34 600 111 222",
                    "address": "Calle Mayor 1, Madrid",
                    "department_id": "dept-1",
                },
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_complete_profile_accepts_a_valid_payload_without_the_optional_company_phone():
    class FakeCompleteProfileUseCase:
        async def execute(self, *, user_id, role, step_id, profile):
            assert profile.company_phone is None

            class _Progress:
                id = "progress-1"
                status = "completed"
                progress_pct = 100
                started_at = None
                completed_at = "2026-07-18T10:00:00Z"

            progress = _Progress()
            progress.step_id = step_id
            return progress

    app.dependency_overrides[onboarding_dependencies.get_complete_profile_use_case] = (
        lambda: FakeCompleteProfileUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-profile/complete-profile",
                json={
                    "full_name": "Sandra Ramírez",
                    "birth_date": "1990-05-20",
                    "dni_nie": "12345678Z",
                    "personal_phone": "+34 600 111 222",
                    "address": "Calle Mayor 1, Madrid",
                    "department_id": "dept-1",
                },
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_externo_invitado_can_reach_get_me():
    class FakeGetMyOnboardingUseCase:
        async def execute(self, *, user_id, role):
            return []

    app.dependency_overrides[onboarding_dependencies.get_my_onboarding_use_case] = (
        lambda: FakeGetMyOnboardingUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/onboarding/me",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
            assert response.status_code == 200
            assert response.json() == {"steps": []}
    finally:
        app.dependency_overrides.clear()


def test_socio_can_reach_get_me_like_any_internal_role():
    """socio [migración 024] = igual que empleado -> onboarding COMPLETO,
    no el parcial del externo-invitado."""

    class FakeGetMyOnboardingUseCase:
        async def execute(self, *, user_id, role):
            return []

    app.dependency_overrides[onboarding_dependencies.get_my_onboarding_use_case] = (
        lambda: FakeGetMyOnboardingUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/onboarding/me",
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_socio_can_submit_quiz_like_any_internal_role():
    class FakeSubmitQuizUseCase:
        async def execute(self, *, user_id, role, step_id, answers):
            class _Attempt:
                pass

            attempt = _Attempt()
            attempt.step_id = step_id
            attempt.score = 1.0
            attempt.passed = True
            attempt.submitted_at = "2026-07-16T10:00:00Z"
            return attempt

    app.dependency_overrides[onboarding_dependencies.get_submit_quiz_use_case] = (
        lambda: FakeSubmitQuizUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-quiz/quiz",
                json={"answers": {"q1": "7"}},
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_socio_cannot_reach_any_admin_endpoint():
    """socio no hereda "Administración" — ni siquiera el catálogo de
    onboarding en modo lectura de gestión."""
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_token_for('socio')}"}
            list_response = client.get("/onboarding/admin/steps", headers=headers)
            progress_response = client.get("/onboarding/admin/progress", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 403
    assert progress_response.status_code == 403


def test_unauthenticated_request_is_rejected():
    try:
        with TestClient(app) as client:
            response = client.get("/onboarding/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_empleado_cannot_list_admin_steps():
    """Ocultar el ítem del navbar no basta — el backend debe rechazar el
    rol equivocado aunque escriba la URL a mano."""
    try:
        with TestClient(app) as client:
            response = client.get(
                "/onboarding/admin/steps",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_cannot_patch_admin_step():
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/onboarding/admin/steps/step-video",
                json={"is_active": False},
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_cannot_get_admin_progress_overview():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/onboarding/admin/progress",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_cannot_reset_quiz_attempt():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/admin/steps/step-quiz/reset-quiz",
                json={"user_id": "user-2"},
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_reach_any_admin_endpoint():
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_token_for('externo_invitado')}"}
            responses = [
                client.get("/onboarding/admin/steps", headers=headers),
                client.get("/onboarding/admin/progress", headers=headers),
            ]
    finally:
        app.dependency_overrides.clear()

    assert all(response.status_code == 403 for response in responses)


def test_administrador_can_list_admin_steps():
    class FakeListOnboardingStepsForAdminUseCase:
        async def execute(self):
            return []

    app.dependency_overrides[
        onboarding_dependencies.get_list_onboarding_steps_admin_use_case
    ] = lambda: FakeListOnboardingStepsForAdminUseCase()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/onboarding/admin/steps",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 200
            assert response.json() == {"steps": []}
    finally:
        app.dependency_overrides.clear()


# --- POST /steps/{step_id}/documents — self-upload del documento firmado
# del paso 3 (sdd/docs-firmados-upload-drive, reemplaza a `/sign`). ---


def _signed_pdf_file() -> dict:
    return {"file": ("firmado.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}


class _FakeUploadSignedDocumentUseCase:
    def __init__(
        self,
        upload: Optional[OnboardingDocumentUpload] = None,
        error: Optional[Exception] = None,
    ):
        self._upload = upload or OnboardingDocumentUpload(
            id="upload-1",
            user_id="user-1",
            onboarding_document_id="doc-signature",
            employee_document_id="employee-doc-1",
            uploaded_at=datetime.now(timezone.utc),
        )
        self._error = error
        self.received_kwargs: Optional[dict] = None

    async def execute(self, **kwargs):
        self.received_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._upload


def test_externo_invitado_cannot_upload_signed_document():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-signature/documents",
                files=_signed_pdf_file(),
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_empleado_can_upload_signed_document():
    fake_use_case = _FakeUploadSignedDocumentUseCase()
    app.dependency_overrides[
        onboarding_dependencies.get_upload_signed_document_use_case
    ] = lambda: fake_use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-signature/documents",
                files=_signed_pdf_file(),
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["employee_document_id"] == "employee-doc-1"
    # `user_id` viene SIEMPRE del JWT (`current_user["sub"]`) — el endpoint
    # ni siquiera declara un campo de formulario para el dueño del
    # documento, así que no hay canal para suplantar a otro usuario.
    assert fake_use_case.received_kwargs["user_id"] == "user-1"


def test_upload_signed_document_ignores_any_user_id_field_sent_in_the_payload():
    """Anti-suplantación (RGPD): aunque un cliente manipulado envíe
    `user_id` en el multipart, el endpoint no lo lee de ningún lado — el
    caso de uso recibe SIEMPRE el `sub` del token, nunca un valor del
    payload."""
    fake_use_case = _FakeUploadSignedDocumentUseCase()
    app.dependency_overrides[
        onboarding_dependencies.get_upload_signed_document_use_case
    ] = lambda: fake_use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/onboarding/steps/step-signature/documents",
                data={"user_id": "user-2"},
                files=_signed_pdf_file(),
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert fake_use_case.received_kwargs["user_id"] == "user-1"
    assert fake_use_case.received_kwargs["user_id"] != "user-2"


def test_administrador_can_get_progress_overview():
    class FakeGetOnboardingProgressOverviewUseCase:
        async def execute(self):
            return []

    app.dependency_overrides[
        onboarding_dependencies.get_onboarding_progress_overview_use_case
    ] = lambda: FakeGetOnboardingProgressOverviewUseCase()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/onboarding/admin/progress",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 200
            assert response.json() == {"employees": []}
    finally:
        app.dependency_overrides.clear()
