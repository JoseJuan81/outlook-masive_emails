"""Outlook Desktop adapter that preserves the current COM sending behavior."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from domain.entities import EmailMessage
from env import load_project_env
from ports.email_sender_port import EmailSenderPort

load_project_env()

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BODY_IMAGES_DIR = _PROJECT_ROOT / "html/images/body"


class OutlookDesktopAdapter(EmailSenderPort):
    """Send emails through Outlook Desktop using the existing COM sequence."""

    def __init__(self, outlook_client=None) -> None:
        self.outlook = outlook_client or self._create_outlook_client()

    def send(self, email: EmailMessage) -> None:
        mail = self.outlook.CreateItem(0)
        sender_email = os.getenv("OUTLOOK_SENDER_EMAIL")
        account = self._find_account(sender_email) if sender_email else None

        if account is not None:
            mail.SendUsingAccount = account
            logger.debug("Outlook account selected -> smtp=%r", sender_email)
        elif sender_email:
            logger.warning("Outlook account not found -> smtp=%r", sender_email)

        mail.Subject = email.subject
        mail.To = email.to
        self._attach_body_images(mail)
        mail.HTMLBody = email.html_body
        logger.debug("Outlook send start -> to=%r, subject=%r", email.to, email.subject)
        try:
            mail.Send()
            logger.debug("Outlook send ok -> to=%r", email.to)
        except Exception as error:
            logger.error("Outlook send error -> to=%r, error=%r", email.to, error)
            raise

        try:
            logger.debug("Outlook send details -> %s", self._collect_mail_debug_info(mail))
        except Exception as error:
            logger.debug("Outlook send details unavailable -> to=%r, error=%r", email.to, error)

    def _attach_body_images(self, mail) -> None:
        """Adjunta imágenes del cuerpo como inline CID. El HTML ya trae referencias cid:image_N."""
        images = sorted(
            (f for f in _BODY_IMAGES_DIR.iterdir() if f.is_file() and not f.name.endswith(".Identifier")),
            key=lambda f: f.name,
        )
        cid_prop = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
        hidden_prop = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
        for idx, image_path in enumerate(images):
            att = mail.Attachments.Add(str(image_path))
            att.PropertyAccessor.SetProperty(cid_prop, f"image_{idx}")
            att.PropertyAccessor.SetProperty(hidden_prop, True)
            logger.debug("Imagen adjunta -> cid=image_%d, archivo=%s", idx, image_path.name)

    def _create_outlook_client(self):
        import win32com.client as win32

        return win32.Dispatch("outlook.application")

    def _find_account(self, sender_email: str):
        for account in self.outlook.Session.Accounts:
            smtp_address = getattr(account, "SmtpAddress", "")
            if smtp_address and smtp_address.lower() == sender_email.lower():
                return account

        return None

    def _collect_mail_debug_info(self, mail) -> dict:
        return {
            "entry_id": getattr(mail, "EntryID", None),
            "sent": getattr(mail, "Sent", None),
            "creation_time": getattr(mail, "CreationTime", None),
            "sent_on": getattr(mail, "SentOn", None),
        }
