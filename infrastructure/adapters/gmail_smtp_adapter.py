"""Gmail SMTP adapter."""

from __future__ import annotations

import os
import smtplib

from email.message import EmailMessage as MimeEmailMessage

from env import load_project_env
from domain.entities import EmailMessage
from ports.email_sender_port import EmailSenderPort

load_project_env()


class GmailSmtpAdapter(EmailSenderPort):
    """Send emails through Gmail SMTP using an app password."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        from_address: str | None = None,
        host: str = "smtp.gmail.com",
        port: int = 465,
    ) -> None:
        self.username = username or os.getenv("GMAIL_SMTP_USERNAME")
        self.password = password or os.getenv("GMAIL_SMTP_APP_PASSWORD")
        self.from_address = from_address or os.getenv("GMAIL_FROM_ADDRESS") or self.username
        self.host = host
        self.port = port

    def send(self, email: EmailMessage) -> None:
        message = MimeEmailMessage()
        message["Subject"] = email.subject
        message["From"] = self.from_address
        message["To"] = email.to
        message.set_content("Este correo requiere un cliente compatible con HTML.")
        message.add_alternative(email.html_body, subtype="html")

        with smtplib.SMTP_SSL(self.host, self.port) as smtp:
            smtp.login(self.username, self.password)
            smtp.send_message(message)
