from infrastructure.adapters.outlook_desktop_adapter import OutlookDesktopAdapter
from domain.entities import EmailMessage


class FakePropertyAccessor:
    def __init__(self):
        self.properties = {}

    def SetProperty(self, key, value):
        self.properties[key] = value


class FakeAttachment:
    def __init__(self, path):
        self.path = path
        self.PropertyAccessor = FakePropertyAccessor()


class FakeAttachments:
    def __init__(self):
        self.items = []

    def Add(self, path):
        att = FakeAttachment(path)
        self.items.append(att)
        return att


class FakeSentFolder:
    pass


class FakeDeliveryStore:
    def GetDefaultFolder(self, folder_id):
        return FakeSentFolder()


class FakeAccount:
    def __init__(self, smtp_address):
        self.SmtpAddress = smtp_address
        self.DeliveryStore = FakeDeliveryStore()


class FakeSession:
    def __init__(self, accounts):
        self.Accounts = accounts


class FakeMailItem:
    def __init__(self):
        self.Subject = None
        self.HTMLBody = None
        self.To = None
        self.SendUsingAccount = None
        self.SaveSentMessageFolder = None
        self.OriginatorDeliveryReportRequested = False
        self.Attachments = FakeAttachments()
        self.EntryID = "entry-123"
        self.Sent = True
        self.CreationTime = "2026-04-12 10:00:00"
        self.SentOn = "2026-04-12 10:00:01"
        self.send_called = False

    def Send(self):
        self.send_called = True


class FakeOutlook:
    def __init__(self, accounts):
        self.Session = FakeSession(accounts)
        self.created_items = []

    def CreateItem(self, item_type):
        assert item_type == 0
        item = FakeMailItem()
        self.created_items.append(item)
        return item


def test_outlook_adapter_uses_matching_send_account(monkeypatch):
    monkeypatch.setenv("OUTLOOK_SENDER_EMAIL", "sender@example.com")
    fake_outlook = FakeOutlook([
        FakeAccount("other@example.com"),
        FakeAccount("sender@example.com"),
    ])
    adapter = OutlookDesktopAdapter(outlook_client=fake_outlook)

    adapter.send(EmailMessage(
        subject="Test subject",
        to="target@example.com",
        html_body="<p>Hello</p>",
    ))

    mail = fake_outlook.created_items[0]
    assert mail.SendUsingAccount.SmtpAddress == "sender@example.com"
    assert mail.send_called is True
    assert mail.OriginatorDeliveryReportRequested is True
    assert isinstance(mail.SaveSentMessageFolder, FakeSentFolder)


def test_outlook_adapter_send_with_tracking_returns_info(monkeypatch):
    monkeypatch.setenv("OUTLOOK_SENDER_EMAIL", "")
    fake_outlook = FakeOutlook([])
    adapter = OutlookDesktopAdapter(outlook_client=fake_outlook)

    result = adapter.send_with_tracking(EmailMessage(
        subject="Test",
        to="target@example.com",
        html_body="<p>Hi</p>",
    ))

    assert result["entry_id"] == "entry-123"
    assert result["sent_on"] == "2026-04-12 10:00:01"


def test_outlook_adapter_collects_debug_info():
    adapter = OutlookDesktopAdapter(outlook_client=FakeOutlook([]))
    mail = FakeMailItem()

    debug_info = adapter._collect_mail_debug_info(mail)

    assert debug_info == {
        "entry_id": "entry-123",
        "sent": True,
        "creation_time": "2026-04-12 10:00:00",
        "sent_on": "2026-04-12 10:00:01",
    }
