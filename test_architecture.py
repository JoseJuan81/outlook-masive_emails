from application.send_emails import SendEmails
from domain.entities import EmailMessage
from infrastructure.repositories.multi_contact_repository import MultiContactRepository


class DummyRepository:
    def __init__(self, contacts):
        self.contacts = contacts

    def get_contacts(self):
        return self.contacts


class DummySender:
    def __init__(self):
        self.sent = []

    def send(self, email):
        assert isinstance(email, EmailMessage)
        self.sent.append(email)


class DummyBuilder:
    def build(self, first_name: str) -> str:
        return f"<p>Hola {first_name}</p>"


def test_multi_contact_repository_removes_duplicate_emails():
    repository = MultiContactRepository([
        DummyRepository([
            {"Nombre": "Alice Smith", "Correo": "alice@example.com"},
            {"Nombre": "Bob Jones", "Correo": "bob@example.com"},
        ]),
        DummyRepository([
            {"Nombre": "Alice Smith", "Correo": "ALICE@example.com"},
            {"Nombre": "Carol Doe", "Correo": "carol@example.com"},
        ]),
    ])

    contacts = repository.get_contacts()

    assert len(contacts) == 3
    assert [contact["Correo"] for contact in contacts] == [
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
    ]


def test_send_emails_use_case_builds_and_sends_messages():
    sender = DummySender()
    use_case = SendEmails(
        contact_repository=DummyRepository([
            {"Nombre": "José Juan", "Correo": "dominguez.josejuan@gmail.com"},
        ]),
        email_sender=sender,
        html_builder=DummyBuilder(),
        confirm_callback=lambda test_mode, contacts_len: "S",
    )

    use_case.execute(subject="Test", test_mode=True)

    assert len(sender.sent) == 1
    assert sender.sent[0].subject == "Test"
    assert sender.sent[0].to == "dominguez.josejuan@gmail.com"
    assert sender.sent[0].html_body == "<p>Hola José</p>"
