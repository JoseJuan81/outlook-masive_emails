import builtins

from main import run


class DummyRepository:
    def __init__(self, contacts):
        self.contacts = contacts

    def get_contacts(self):
        return self.contacts


class FakeMailItem:
    def __init__(self):
        self.Subject = None
        self.HTMLBody = None
        self.To = None
        self.display_called = False
        self.send_called = False

    def Display(self):
        self.display_called = True

    def Send(self):
        self.send_called = True


class FakeOutlook:
    def __init__(self):
        self.created_items = []

    def CreateItem(self, item_type):
        assert item_type == 0
        item = FakeMailItem()
        self.created_items.append(item)
        return item


def test_main_flow_builds_and_sends_with_outlook_and_airtable_shape(monkeypatch):
    fake_outlook = FakeOutlook()
    repository = DummyRepository([
        {"Nombre": "José Juan", "Correo": "dominguez.josejuan@gmail.com"},
    ])

    monkeypatch.setattr(builtins, "input", lambda _: "S")

    run(
        repository=repository,
        outlook_client=fake_outlook,
        subject="Int-elle Corporation en Navidad",
        test_mode=True,
    )

    assert len(fake_outlook.created_items) == 1
    mail = fake_outlook.created_items[0]
    assert mail.Subject == "Int-elle Corporation en Navidad"
    assert mail.To == "dominguez.josejuan@gmail.com"
    assert "José" in mail.HTMLBody
    assert mail.display_called is True
    assert mail.send_called is True
