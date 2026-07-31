import pytest

from src.features.email_templates.application.use_cases.manage_email_templates import (
    ListEmailTemplatesUseCase,
    PreviewEmailTemplateUseCase,
    RestoreEmailTemplateUseCase,
    UpdateEmailTemplateUseCase,
)
from src.features.email_templates.domain.errors import (
    EmailTemplateNotFoundError,
    InvalidEmailTemplateError,
)

from .fakes import FakeEmailTemplateRepository, build_template

FRONTEND = "https://intranet.ameliahub.com"


class TestUpdate:
    @pytest.mark.asyncio
    async def test_saves_the_admin_text(self):
        repository = FakeEmailTemplateRepository()
        use_case = UpdateEmailTemplateUseCase(repository)

        updated = await use_case.execute(
            "staff_invited",
            subject="Bienvenida a Amelia, {{full_name}}",
            body="Nos alegra tenerte.",
            updated_by="admin-1",
        )

        assert updated.subject == "Bienvenida a Amelia, {{full_name}}"
        assert updated.updated_by == "admin-1"

    @pytest.mark.asyncio
    async def test_saving_reactivates_a_restored_template(self):
        """Editar una plantilla que estaba en "texto por defecto" es querer volver
        a usar la personalizada. Sin esto, el admin guardaría un cambio y no vería
        ningún efecto en los correos."""
        repository = FakeEmailTemplateRepository([build_template(is_active=False)])
        use_case = UpdateEmailTemplateUseCase(repository)

        updated = await use_case.execute(
            "staff_invited", subject="Nuevo", body="Nuevo"
        )

        assert updated.is_active is True

    @pytest.mark.asyncio
    async def test_rejects_an_empty_subject(self):
        """Pasa el tipo (`str`) pero deja la línea del asunto en blanco en la
        bandeja de entrada."""
        use_case = UpdateEmailTemplateUseCase(FakeEmailTemplateRepository())

        with pytest.raises(InvalidEmailTemplateError):
            await use_case.execute("staff_invited", subject="   ", body="x")

    @pytest.mark.asyncio
    async def test_rejects_an_empty_body(self):
        use_case = UpdateEmailTemplateUseCase(FakeEmailTemplateRepository())

        with pytest.raises(InvalidEmailTemplateError):
            await use_case.execute("staff_invited", subject="Asunto", body="  ")

    @pytest.mark.asyncio
    async def test_trims_the_saved_text(self):
        repository = FakeEmailTemplateRepository()
        use_case = UpdateEmailTemplateUseCase(repository)

        updated = await use_case.execute(
            "staff_invited", subject="  Asunto  ", body="  x  "
        )

        assert updated.subject == "Asunto"
        assert updated.body == "x"

    @pytest.mark.asyncio
    async def test_an_unknown_key_is_not_found(self):
        """El catálogo es CERRADO: lo siembra la migración con los tipos de correo
        que el código sabe enviar, así que esto es un id inventado y no una
        plantilla por crear."""
        use_case = UpdateEmailTemplateUseCase(FakeEmailTemplateRepository())

        with pytest.raises(EmailTemplateNotFoundError):
            await use_case.execute("no_existe", subject="A", body="B")


class TestRestore:
    @pytest.mark.asyncio
    async def test_deactivates_without_losing_the_admin_text(self):
        """Restaurar NO borra: el texto que el admin había escrito se conserva por
        si quiere volver a él."""
        repository = FakeEmailTemplateRepository(
            [build_template(subject="Mi asunto", body="Mi texto")]
        )
        use_case = RestoreEmailTemplateUseCase(repository)

        restored = await use_case.execute("staff_invited", updated_by="admin-1")

        assert restored.is_active is False
        assert restored.subject == "Mi asunto"
        assert restored.body == "Mi texto"

    @pytest.mark.asyncio
    async def test_an_unknown_key_is_not_found(self):
        use_case = RestoreEmailTemplateUseCase(FakeEmailTemplateRepository())

        with pytest.raises(EmailTemplateNotFoundError):
            await use_case.execute("no_existe")


class TestPreview:
    @pytest.mark.asyncio
    async def test_renders_the_draft_not_what_is_saved(self):
        """Lo que evita que el admin descubra una errata cuando el correo ya salió
        a toda la plantilla."""
        repository = FakeEmailTemplateRepository()
        use_case = PreviewEmailTemplateUseCase(repository, frontend_url=FRONTEND)

        subject, html = await use_case.execute(
            "staff_invited",
            subject="Borrador para {{full_name}}",
            body="Texto en borrador",
        )

        assert subject == "Borrador para Ana Ejemplo"
        assert "Texto en borrador" in html

    @pytest.mark.asyncio
    async def test_uses_example_data_never_a_real_person(self):
        """Previsualizar con los datos de alguien de la plantilla expondría sus
        datos en una pantalla que no es su ficha."""
        use_case = PreviewEmailTemplateUseCase(
            FakeEmailTemplateRepository(), frontend_url=FRONTEND
        )

        subject, _ = await use_case.execute(
            "staff_invited", subject="{{full_name}} · {{job_title}}"
        )

        assert subject == "Ana Ejemplo · Project Manager"

    @pytest.mark.asyncio
    async def test_previews_a_restored_template_with_its_custom_text(self):
        """Si la plantilla está en "texto por defecto" y el admin escribe un
        borrador, la previsualización debe mostrar SU borrador — devolverle el
        texto de fábrica sin explicar por qué sería desconcertante."""
        repository = FakeEmailTemplateRepository([build_template(is_active=False)])
        use_case = PreviewEmailTemplateUseCase(repository, frontend_url=FRONTEND)

        subject, _ = await use_case.execute("staff_invited", subject="Mi borrador")

        assert subject == "Mi borrador"

    @pytest.mark.asyncio
    async def test_the_preview_keeps_the_email_frame(self):
        """Se previsualiza lo que va a RECIBIR el destinatario, no una
        aproximación: el marco (logo, CTA, pie) forma parte del correo."""
        use_case = PreviewEmailTemplateUseCase(
            FakeEmailTemplateRepository(), frontend_url=FRONTEND
        )

        _, html = await use_case.execute("staff_invited", body="x")

        assert "<html" in html.lower()
        assert FRONTEND in html

    @pytest.mark.asyncio
    async def test_it_does_not_save_anything(self):
        repository = FakeEmailTemplateRepository()
        before = repository.templates["staff_invited"]
        use_case = PreviewEmailTemplateUseCase(repository, frontend_url=FRONTEND)

        await use_case.execute("staff_invited", subject="Otro asunto")

        assert repository.templates["staff_invited"] == before

    @pytest.mark.asyncio
    async def test_an_unknown_key_is_not_found(self):
        use_case = PreviewEmailTemplateUseCase(
            FakeEmailTemplateRepository(), frontend_url=FRONTEND
        )

        with pytest.raises(EmailTemplateNotFoundError):
            await use_case.execute("no_existe")


class TestList:
    @pytest.mark.asyncio
    async def test_includes_the_restored_ones(self):
        """Las restauradas son las que están usando el texto por defecto: el admin
        tiene que verlas para poder reactivarlas."""
        repository = FakeEmailTemplateRepository(
            [
                build_template(template_key="a", label="A", is_active=True),
                build_template(template_key="b", label="B", is_active=False),
            ]
        )

        templates = await ListEmailTemplatesUseCase(repository).execute()

        assert [t.template_key for t in templates] == ["a", "b"]
