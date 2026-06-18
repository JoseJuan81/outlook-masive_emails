from pathlib import Path

from application.send_emails import SendEmails
from infrastructure.services.html_preview_service import HtmlPreviewService


class DummyRepository:
    def __init__(self, contacts):
        self.contacts = contacts

    def get_contacts(self):
        return self.contacts


class DummySender:
    def __init__(self):
        self.sent = []

    def send(self, email):
        self.sent.append(email)


class DummyBuilder:
    def build(self, first_name: str) -> str:
        return f"<html><body>Hola {first_name}</body></html>"


def test_preview_service_writes_html_file(tmp_path):
    service = HtmlPreviewService(output_dir=tmp_path)

    preview_path = service.generate_preview("<html>ok</html>")

    assert preview_path.exists()
    assert preview_path.read_text(encoding="utf-8") == "<html>ok</html>"


def test_send_emails_generates_preview_and_sends_after_approval(tmp_path):
    preview_calls = []

    def preview_callback(preview_path: Path, preview_contact) -> bool:
        preview_calls.append((preview_path, preview_contact))
        return True

    sender = DummySender()
    use_case = SendEmails(
        contact_repository=DummyRepository([
            {"Nombre": "José Juan", "Correo": "dominguez.josejuan@gmail.com"},
        ]),
        email_sender=sender,
        html_builder=DummyBuilder(),
        confirm_callback=lambda test_mode, contacts_len: "S",
        preview_service=HtmlPreviewService(output_dir=tmp_path),
        preview_callback=preview_callback,
    )

    use_case.execute(
        subject="Test",
        test_mode=True,
        preview_before_send=True,
        preview_open_in_browser=False,
    )

    assert len(preview_calls) == 1
    preview_path, preview_contact = preview_calls[0]
    assert preview_path.exists()
    assert preview_contact.name == "José Juan"
    assert len(sender.sent) == 1


def test_send_emails_cancels_when_preview_not_approved(tmp_path):
    sender = DummySender()
    use_case = SendEmails(
        contact_repository=DummyRepository([
            {"Nombre": "José Juan", "Correo": "dominguez.josejuan@gmail.com"},
        ]),
        email_sender=sender,
        html_builder=DummyBuilder(),
        confirm_callback=lambda test_mode, contacts_len: "S",
        preview_service=HtmlPreviewService(output_dir=tmp_path),
        preview_callback=lambda preview_path, preview_contact: False,
    )

    use_case.execute(
        subject="Test",
        test_mode=True,
        preview_before_send=True,
        preview_open_in_browser=False,
    )

    assert len(sender.sent) == 0
