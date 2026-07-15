import pytest

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from .fakes import FakeEmailSender, FakeNotificationRepository


@pytest.mark.asyncio
async def test_notify_creates_one_row_per_recipient_and_sends_one_email_each():
    repository = FakeNotificationRepository()
    repository.emails_by_user = {"user-1": "a@ameliahub.com", "user-2": "b@ameliahub.com"}
    email_sender = FakeEmailSender()
    use_case = NotifyUseCase(repository, email_sender)

    notifications = await use_case.execute(
        recipient_ids=["user-1", "user-2"],
        type="announcement_published",
        title="Nuevo anuncio",
        data={"url": "/inicio"},
    )

    assert len(notifications) == 2
    assert {n.user_id for n in notifications} == {"user-1", "user-2"}
    assert len(email_sender.sent) == 2
    assert {e["to"] for e in email_sender.sent} == {"a@ameliahub.com", "b@ameliahub.com"}


@pytest.mark.asyncio
async def test_notify_skips_email_when_recipient_has_no_email_on_file():
    repository = FakeNotificationRepository()  # sin emails registrados
    email_sender = FakeEmailSender()
    use_case = NotifyUseCase(repository, email_sender)

    notifications = await use_case.execute(
        recipient_ids=["user-1"], type="mailbox_message", title="Nuevo mensaje"
    )

    assert len(notifications) == 1
    assert email_sender.sent == []


@pytest.mark.asyncio
async def test_notify_survives_an_email_failure_without_losing_the_in_app_notification():
    repository = FakeNotificationRepository()
    repository.emails_by_user = {"user-1": "broken@ameliahub.com"}
    email_sender = FakeEmailSender(fail_for={"broken@ameliahub.com"})
    use_case = NotifyUseCase(repository, email_sender)

    notifications = await use_case.execute(
        recipient_ids=["user-1"], type="absence_approved", title="Tu ausencia fue aprobada"
    )

    # El email falló pero la notificación in-app ya está creada — es la
    # garantía mínima, el email es best-effort (ver docstring de NotifyUseCase).
    assert len(notifications) == 1
    assert email_sender.sent == []


@pytest.mark.asyncio
async def test_notify_can_skip_email_explicitly():
    repository = FakeNotificationRepository()
    repository.emails_by_user = {"user-1": "a@ameliahub.com"}
    email_sender = FakeEmailSender()
    use_case = NotifyUseCase(repository, email_sender)

    await use_case.execute(
        recipient_ids=["user-1"], type="birthday", title="¡Feliz cumpleaños!", send_email=False
    )

    assert email_sender.sent == []


@pytest.mark.asyncio
async def test_notify_admins_resolves_recipients_from_the_repository():
    repository = FakeNotificationRepository()
    repository.admin_ids = ["admin-1", "admin-2"]
    use_case = NotifyUseCase(repository, FakeEmailSender())

    notifications = await use_case.notify_admins(
        type="absence_requested", title="Nueva solicitud de ausencia"
    )

    assert {n.user_id for n in notifications} == {"admin-1", "admin-2"}


@pytest.mark.asyncio
async def test_notify_team_excluding_role_resolves_recipients_from_the_repository():
    repository = FakeNotificationRepository()
    repository.active_user_ids_by_excluded_role = {"externo_invitado": ["user-1", "user-2"]}
    use_case = NotifyUseCase(repository, FakeEmailSender())

    notifications = await use_case.notify_team_excluding_role(
        "externo_invitado", type="announcement_published", title="Nuevo anuncio"
    )

    assert {n.user_id for n in notifications} == {"user-1", "user-2"}


@pytest.mark.asyncio
async def test_notify_announcement_resolves_recipients_scoped_to_the_audience():
    repository = FakeNotificationRepository()
    repository.announcement_recipients = {
        ("entity", "entity-hub", None): ["user-hub-1", "user-hub-2"],
    }
    use_case = NotifyUseCase(repository, FakeEmailSender())

    notifications = await use_case.notify_announcement(
        audience="entity",
        entity_id="entity-hub",
        role_id=None,
        type="announcement_published",
        title="Nuevo anuncio",
    )

    assert {n.user_id for n in notifications} == {"user-hub-1", "user-hub-2"}


@pytest.mark.asyncio
async def test_notify_announcement_with_audience_all_ignores_entity_and_role():
    repository = FakeNotificationRepository()
    repository.announcement_recipients = {("all", None, None): ["user-1", "user-2", "user-3"]}
    use_case = NotifyUseCase(repository, FakeEmailSender())

    notifications = await use_case.notify_announcement(
        audience="all", entity_id=None, role_id=None, type="announcement_published", title="Nuevo anuncio"
    )

    assert {n.user_id for n in notifications} == {"user-1", "user-2", "user-3"}
