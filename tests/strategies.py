"""Mock infrastructure + mirror of send_from_staging.main() for testing.

Why a "mirror"? `send_from_staging.py` is a standalone Windows-only script
that imports `win32com.client` at runtime. Patching that import is fragile
and requires careful `sys.modules` manipulation. Instead, this module
re-implements the *exact same dispatch logic* the script performs, but with
``MockOutlook`` injected. This mirrors the production code line-by-line; if
production drifts, this mirror drifts too (kept in sync by a watcher test
in test_outlook_com_order.py).

DOCUMENTED MIRROR ANCHORS (line numbers of send_from_staging.py as of
the time this test was written; the watcher test asserts they still hold):

    M1: mail = outlook.CreateItem(0)                    -> send_from_staging.py:427
    M2: if account: mail.SendUsingAccount = account     -> send_from_staging.py:429
    M3: mail.PropertyAccessor.SetProperty(              -> send_from_staging.py:440
            "http://schemas.microsoft.com/mapi/proptag/0x0037001F",
            item["subject"],
        )
    M4: mail.To = item["to"]                             -> send_from_staging.py:446
    M8: mail.ReadReceiptRequested = False                -> send_from_staging.py:447
    M5: for idx, img_path in enumerate(images):          -> send_from_staging.py:449
            att = mail.Attachments.Add(str(img_path))
            att.PropertyAccessor.SetProperty(_CID_PROP, f"image_{idx}")
            att.PropertyAccessor.SetProperty(_HIDDEN_PROP, True)
    M6: mail.Subject = item["subject"]                   -> send_from_staging.py:455
    M7: mail.HTMLBody = item["html"]                     -> send_from_staging.py:456
    M9: mail.Send()                                      -> send_from_staging.py:460

M8 (mail.ReadReceiptRequested = False) es la línea que este espejo había
perdido: producción la apagaba para que Outlook no pidiera acuse de lectura
y el espejo no la reproducía. Un espejo que se queda sin una línea deja de
servir de referencia, así que va sincronizada y con su watcher.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# Mirror of send_from_staging.py constants we care about for assertions.
PROPTAG_SUBJECT = "http://schemas.microsoft.com/mapi/proptag/0x0037001F"
CID_PROP = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
HIDDEN_PROP = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"


# ---------------------------------------------------------------------------
# Mock objects
# ---------------------------------------------------------------------------

@dataclass
class MockAttachment:
    parent: "MockMailItem"
    path: str
    cid: Optional[str] = None
    hidden: Optional[bool] = None
    properties: list[tuple[str, Any]] = field(default_factory=list)

    @property
    def PropertyAccessor(self) -> "_PropertyAccessor":
        return _PropertyAccessor(self)

    def add_property(self, name: str, value: Any) -> None:
        self.properties.append((name, value))


@dataclass
class _PropertyAccessor:
    target: Any  # MockMailItem or MockAttachment

    def SetProperty(self, name: str, value: Any) -> None:
        # Record on a call log attached to whatever we're setting on.
        log = getattr(self.target, "_property_log", None)
        if log is not None:
            log.append({"name": name, "value": value})
        # Special-case attachments: also stash cid/hidden for convenience.
        if isinstance(self.target, MockAttachment):
            if name == CID_PROP:
                self.target.cid = value
            elif name == HIDDEN_PROP:
                self.target.hidden = value
            self.target.add_property(name, value)


@dataclass
class MockMailItem:
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    _property_log: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[MockAttachment] = field(default_factory=list)
    To: str = ""
    Subject: str = ""
    HTMLBody: str = ""
    # Lo que producción debe dejar en False. El default es None (no "False")
    # para que el test distinga "el espejo no lo puso" de "el espejo lo puso".
    ReadReceiptRequested: bool | None = None
    OriginatorDeliveryReportRequested: bool = False
    SendUsingAccount: Any = None
    SaveSentMessageFolder: Any = None
    _created_with: Optional[int] = None

    @property
    def PropertyAccessor(self) -> _PropertyAccessor:
        return _PropertyAccessor(self)

    def CreateItem(self, kind: int) -> "MockMailItem":
        self._created_with = kind
        return MockMailItem(_created_with=kind)

    def Attachments_Add(self, path: str) -> MockAttachment:
        att = MockAttachment(parent=self, path=path)
        self.attachments.append(att)
        return att

    @property
    def Attachments(self) -> "_AttachmentsCollection":
        return _AttachmentsCollection(self)

    def Save(self) -> None:
        self.calls.append(("Save", ()))

    def Send(self) -> None:
        self.calls.append(("Send", ()))


@dataclass
class _AttachmentsCollection:
    mail: MockMailItem

    def Add(self, path: str) -> MockAttachment:
        return self.mail.Attachments_Add(path)


@dataclass
class MockOutlook:
    """Top-level Outlook mock; tracks everything in self.calls."""
    sent_apps: list[MockMailItem] = field(default_factory=list)
    next_mail: Optional[MockMailItem] = None
    sender_account: Any = None

    def CreateItem(self, kind: int) -> MockMailItem:
        if self.next_mail is not None:
            mail = self.next_mail
            self.next_mail = None
        else:
            mail = MockMailItem()
        mail._created_with = kind
        self.sent_apps.append(mail)
        return mail

    @property
    def Session(self) -> "SessionProxy":
        return SessionProxy(self)


@dataclass
class SessionProxy:
    outlook: MockOutlook

    @property
    def Accounts(self) -> "AccountsCollection":
        return AccountsCollection(self.outlook)


@dataclass
class AccountsCollection:
    outlook: MockOutlook

    def __iter__(self):
        if self.outlook.sender_account is not None:
            yield self.outlook.sender_account


@dataclass
class MockAccount:
    SmtpAddress: str = "sender@example.com"
    DeliveryStore: Any = None


# ---------------------------------------------------------------------------
# Mirror of send_from_staging.main() dispatch loop
# ---------------------------------------------------------------------------

def dispatch_one_mail(
    outlook: MockOutlook,
    item: dict,
    images: list[Path],
    account: Any = None,
) -> MockMailItem:
    """Mirror of the per-email dispatch block in send_from_staging.main().

    The body of this function is the *reference implementation*. Any change
    here MUST be reflected in send_from_staging.py — the watcher test
    asserts the source line numbers to keep them in sync.
    """
    mail = outlook.CreateItem(0)  # M1
    if account:
        mail.SendUsingAccount = account  # M2
        try:
            sf = account.DeliveryStore.GetDefaultFolder(5)
            mail.SaveSentMessageFolder = sf
        except Exception:
            pass

    try:
        mail.PropertyAccessor.SetProperty(
            PROPTAG_SUBJECT,
            item["subject"],
        )  # M3
    except Exception:
        pass

    mail.To = item["to"]  # M4
    mail.ReadReceiptRequested = False  # M8
    mail.OriginatorDeliveryReportRequested = False

    for idx, img_path in enumerate(images):  # M5
        att = mail.Attachments.Add(str(img_path))
        att.PropertyAccessor.SetProperty(CID_PROP, f"image_{idx}")
        att.PropertyAccessor.SetProperty(HIDDEN_PROP, True)

    mail.Subject = item["subject"]  # M6
    mail.HTMLBody = item["html"]  # M7

    mail.Send()  # M9
    return mail


def run_send_from_staging_with_mocks(
    staging_path: Path,
    body_images_dir: Path,
    outlook: Optional[MockOutlook] = None,
    sender_email: str = "sender@example.com",
) -> list[MockMailItem]:
    """Run a mock implementation of send_from_staging.main().

    Reads ``staging_path`` (the JSON written by /api/send), iterates over the
    staged emails and dispatches each via ``dispatch_one_mail``. Returns
    every MockMailItem created, in order.

    This deliberately does NOT import send_from_staging.main(): we mirror the
    logic here so we can run on Linux without win32com. See tests/README.md.
    """
    outlook = outlook or MockOutlook()
    if outlook.sender_account is None:
        outlook.sender_account = MockAccount(SmtpAddress=sender_email)

    emails = json.loads(Path(staging_path).read_text(encoding="utf-8"))
    images = sorted(
        (f for f in body_images_dir.iterdir() if f.is_file() and not f.name.endswith(".Identifier")),
        key=lambda f: f.name,
    ) if body_images_dir.exists() else []

    dispatched: list[MockMailItem] = []
    for item in emails:
        mail = dispatch_one_mail(
            outlook=outlook,
            item=item,
            images=images,
            account=outlook.sender_account,
        )
        dispatched.append(mail)
    return dispatched
