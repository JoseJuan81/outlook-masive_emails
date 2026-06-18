"""Use case for sending emails while preserving the existing behavior."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Protocol

from domain.entities import ContactEntity, EmailMessage
from domain.types import MetadataMap, RawContact

logger = logging.getLogger(__name__)


class HtmlBuilderPort(Protocol):
    """Structural type for the HTML builder used by the use case."""

    def build(self, first_name: str) -> str:
        """Build the final HTML body for a recipient."""


class ConfirmationCallback(Protocol):
    """Structural type for the interactive confirmation callback."""

    def __call__(self, test_mode: bool = True, contacts_len: int = 0) -> str:
        """Return the user confirmation string."""


class HtmlPreviewPort(Protocol):
    """Structural type for generating an HTML preview file."""

    def generate_preview(
        self,
        html: str,
        filename: str = "email_preview.html",
        open_in_browser: bool = False,
    ) -> Path:
        """Write the preview HTML and return its path."""


class PreviewApprovalCallback(Protocol):
    """Structural type for asking the user to approve the rendered preview."""

    def __call__(self, preview_path: Path, preview_contact: ContactEntity) -> bool:
        """Return True when the preview is approved for sending."""


class SendEmails:
    """Application use case that coordinates contact retrieval and email sending."""

    def __init__(
        self,
        contact_repository,
        email_sender,
        html_builder: HtmlBuilderPort,
        confirm_callback: ConfirmationCallback,
        preview_service: HtmlPreviewPort | None = None,
        preview_callback: PreviewApprovalCallback | None = None,
        delay_seconds: float = 2.0,
        max_retries: int = 3,
        tracker=None,
    ) -> None:
        self.contact_repository = contact_repository
        self.email_sender = email_sender
        self.html_builder = html_builder
        self.confirm_callback = confirm_callback
        self.preview_service = preview_service
        self.preview_callback = preview_callback
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.tracker = tracker

    def get_contacts(self) -> list[ContactEntity]:
        """Return contacts normalized for the domain layer."""
        raw_contacts = self.contact_repository.get_contacts()
        contacts: list[ContactEntity] = []

        for contact in raw_contacts:
            if isinstance(contact, ContactEntity):
                contacts.append(contact)
                continue

            name, email, metadata = self._extract_contact_data(contact)
            contacts.append(ContactEntity(name=name, email=email, metadata=metadata))

        return contacts

    def execute(
        self,
        subject: str,
        test_mode: bool,
        preview_before_send: bool = False,
        preview_open_in_browser: bool = False,
    ) -> None:
        """Send an email to each retrieved contact."""
        contacts = self.get_contacts()
        contacts_len = len(contacts)

        if preview_before_send and contacts:
            preview_contact = contacts[0]
            first_name = preview_contact.name.split(" ")[0].title()
            preview_html = self.html_builder.build(first_name)

            if self.preview_service is None or self.preview_callback is None:
                raise RuntimeError("Preview flow requires both preview_service and preview_callback.")

            preview_path = self.preview_service.generate_preview(
                html=preview_html,
                open_in_browser=preview_open_in_browser,
            )
            preview_approved = self.preview_callback(
                preview_path=preview_path,
                preview_contact=preview_contact,
            )

            if not preview_approved:
                logger.info("Envio cancelado: vista previa no aprobada por el usuario")
                return

        user_confirmation = self.confirm_callback(
            test_mode=test_mode,
            contacts_len=contacts_len,
        )

        if user_confirmation.lower() not in ["s", "si", "sí"]:
            logger.info("Envio cancelado por el usuario")
            return

        if self.tracker:
            self.tracker.start_run()

        failed: list[str] = []
        for counter, contact in enumerate(contacts, start=1):
            logger.info(
                "Procesando %d/%d -> %s <%s>",
                counter, contacts_len, contact.name, contact.email,
            )

            first_name = contact.name.split(" ")[0].title()
            html_body = self.html_builder.build(first_name)
            email = EmailMessage(
                subject=subject,
                to=contact.email,
                html_body=html_body,
            )

            sent = self._send_with_retry(email, counter, contacts_len)
            if not sent:
                failed.append(f"{contact.name} <{contact.email}>")

            if counter < contacts_len:
                logger.info("Esperando %.1fs antes del siguiente envio...", self.delay_seconds)
                time.sleep(self.delay_seconds)

        if failed:
            logger.error("Envios fallidos (%d): %s", len(failed), ", ".join(failed))
        logger.info("FIN — enviados: %d/%d", contacts_len - len(failed), contacts_len)

        if self.tracker:
            self.tracker.finish_run()
            self.tracker.print_summary()

    def _send_with_retry(self, email: EmailMessage, counter: int, total: int) -> bool:
        """Attempt to send with exponential backoff. Returns True on success."""
        for attempt in range(1, self.max_retries + 1):
            try:
                entry_id = None
                if hasattr(self.email_sender, "send_with_tracking"):
                    info = self.email_sender.send_with_tracking(email)
                    entry_id = info.get("entry_id")
                else:
                    self.email_sender.send(email)
                logger.info("Enviado %d/%d -> %s", counter, total, email.to)
                if self.tracker:
                    self.tracker.record_sent(email.to, email.subject, entry_id=entry_id)
                return True
            except Exception as exc:
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "Intento %d/%d fallido -> %s | %s | reintentando en %ds",
                        attempt, self.max_retries, email.to, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "FALLO definitivo tras %d intentos -> %s | %s",
                        self.max_retries, email.to, exc,
                    )
                    if self.tracker:
                        self.tracker.record_failed(email.to, email.subject, str(exc), attempt)
        return False

    def _extract_contact_data(self, contact: RawContact) -> tuple[str, str, MetadataMap]:
        """Preserve the original dict iteration behavior used by the old sender."""
        if isinstance(contact, dict):
            name, email, *_ = contact.values()
            return name, email, contact

        if isinstance(contact, (list, tuple)):
            name, email, *_ = contact
            return name, email, {"Nombre": name, "Correo": email}

        raise TypeError(f"Unsupported contact format: {type(contact)!r}")
